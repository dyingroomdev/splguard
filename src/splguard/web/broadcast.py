from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

import discord
import httpx
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from ..config import settings
from ..discordbot.runner import DiscordBotRunner

DISCORD_API_BASE = "https://discord.com/api/v10"
SESSION_COOKIE = "splguard_session"
STATE_COOKIE = "splguard_oauth_state"

router = APIRouter(prefix="/broadcast", tags=["broadcast"])


@dataclass
class SessionUser:
    user_id: int
    username: str
    display: str


def _get_serializer() -> URLSafeSerializer:
    key = settings.session_secret or settings.bot_token
    if not key:
        raise RuntimeError("SESSION_SECRET or BOT_TOKEN must be configured.")
    return URLSafeSerializer(key, salt="splguard-broadcast")


def _require_oauth_config() -> None:
    if not (
        settings.discord_client_id
        and settings.discord_client_secret
        and settings.discord_redirect_uri
        and settings.discord_bot_token
        and settings.discord_guild_id
    ):
        raise HTTPException(
            status_code=503,
            detail="Discord OAuth is not fully configured.",
        )


async def _fetch_discord(
    method: str, path: str, *, headers: dict[str, str] | None = None, **kwargs: Any
) -> httpx.Response:
    final_headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
    if headers:
        final_headers.update(headers)
    url = f"{DISCORD_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(method, url, headers=final_headers, **kwargs)
    return resp


async def _fetch_channels() -> list[dict[str, Any]]:
    resp = await _fetch_discord("GET", f"/guilds/{settings.discord_guild_id}/channels")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to load Discord channels.")
    data = resp.json()
    text_channels = [
        {"id": item["id"], "name": item["name"]}
        for item in data
        if item.get("type") in {0, 5}
    ]
    text_channels.sort(key=lambda c: c["name"].lower())
    return text_channels


async def _fetch_member(user_id: int) -> dict[str, Any]:
    resp = await _fetch_discord(
        "GET",
        f"/guilds/{settings.discord_guild_id}/members/{user_id}",
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=403, detail="You are not a member of SPL Shield.")
    return resp.json()


def _user_is_admin(member: dict[str, Any]) -> bool:
    admin_role_id = settings.discord_say_admin_role_id
    role_ids = {int(role_id) for role_id in member.get("roles", [])}
    if admin_role_id and admin_role_id in role_ids:
        return True
    user_id = int(member["user"]["id"])
    if user_id in settings.discord_admin_ids:
        return True
    return False


def _serialize_session(user: SessionUser) -> str:
    serializer = _get_serializer()
    return serializer.dumps({"user_id": user.user_id, "username": user.username, "display": user.display})


def _deserialize_session(value: str) -> SessionUser | None:
    serializer = _get_serializer()
    try:
        data = serializer.loads(value)
    except BadSignature:
        return None
    return SessionUser(
        user_id=int(data["user_id"]),
        username=data.get("username", ""),
        display=data.get("display", ""),
    )


def _set_cookie(response: RedirectResponse | HTMLResponse, name: str, value: str, max_age: int = 3600) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=max_age,
    )


def _clear_cookie(response: RedirectResponse, name: str) -> None:
    response.delete_cookie(name)


async def _require_session_user(request: Request) -> SessionUser | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    return _deserialize_session(cookie)


@router.get("/login")
async def login() -> RedirectResponse:
    _require_oauth_config()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": settings.discord_client_id,
        "scope": "identify",
        "state": state,
        "redirect_uri": settings.discord_redirect_uri,
        "prompt": "consent",
    }
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"https://discord.com/api/oauth2/authorize?{query}"
    response = RedirectResponse(url)
    _set_cookie(response, STATE_COOKIE, _get_serializer().dumps({"state": state}), max_age=300)
    return response


@router.get("/callback")
async def oauth_callback(code: str, state: str, request: Request) -> RedirectResponse:
    _require_oauth_config()
    stored = request.cookies.get(STATE_COOKIE)
    if not stored:
        raise HTTPException(status_code=400, detail="Missing OAuth state.")
    try:
        data = _get_serializer().loads(stored)
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    if state != data.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch.")

    token_payload = {
        "client_id": settings.discord_client_id,
        "client_secret": settings.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.discord_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.post(
            "https://discord.com/api/oauth2/token",
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange OAuth code.")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access token.")

    async with httpx.AsyncClient(timeout=20) as client:
        user_resp = await client.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch Discord user.")
    user_data = user_resp.json()
    member = await _fetch_member(int(user_data["id"]))
    if not _user_is_admin(member):
        raise HTTPException(status_code=403, detail="You are not authorized to use this tool.")

    display = f"{user_data.get('username')}#{user_data.get('discriminator', '0')}"
    session = SessionUser(
        user_id=int(user_data["id"]),
        username=user_data.get("username", ""),
        display=display,
    )
    response = RedirectResponse("/broadcast", status_code=302)
    _set_cookie(response, SESSION_COOKIE, _serialize_session(session), max_age=86400)
    _clear_cookie(response, STATE_COOKIE)
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/broadcast", status_code=302)
    _clear_cookie(response, SESSION_COOKIE)
    _clear_cookie(response, STATE_COOKIE)
    return response


@router.get("", response_class=HTMLResponse)
async def broadcast_form(request: Request) -> HTMLResponse:
    _require_oauth_config()
    user = await _require_session_user(request)
    if not user:
        return RedirectResponse("/broadcast/login", status_code=302)
    channels = await _fetch_channels()
    options = "\n".join(
        f'<option value="{channel["id"]}">#{channel["name"]}</option>' for channel in channels
    )
    channel_json = json.dumps(channels)
    options = "\n".join(
        f'<option value="#{channel["name"]}">#{channel["name"]}</option>' for channel in channels
    )
    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>SPL Shield Broadcast</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                margin: 0;
                padding: 2rem;
                background: #0b1523;
                color: #f2f5ff;
            }}
            .card {{
                max-width: 720px;
                margin: 0 auto;
                background: #121f33;
                border-radius: 16px;
                padding: 2rem;
                box-shadow: 0 15px 35px rgba(0,0,0,.35);
            }}
            label {{
                display: block;
                margin-bottom: 0.5rem;
                font-weight: 600;
            }}
            select, textarea, input[type="file"] {{
                width: 100%;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.2);
                padding: 0.75rem;
                background: #1a2a45;
                color: #f2f5ff;
                margin-bottom: 1rem;
            }}
            select option {{
                background: #0f1a2b;
                color: #f2f5ff;
            }}
            textarea {{
                min-height: 200px;
                resize: vertical;
            }}
            .actions {{
                display: flex;
                align-items: center;
                gap: 1rem;
            }}
            button {{
                border: none;
                border-radius: 999px;
                padding: 0.75rem 1.75rem;
                font-size: 1rem;
                cursor: pointer;
            }}
            .primary {{
                background: linear-gradient(120deg,#27d2a3,#5865f2);
                color: white;
            }}
            .secondary {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.2);
                color: #f2f5ff;
            }}
            .checkbox {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 1rem;
            }}
            a {{
                color: #6bd6ff;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Broadcast to Discord</h2>
            <p style="opacity:0.8;">Signed in as <strong>{user.display}</strong>. <small><form method="post" action="/broadcast/logout" style="display:inline;"><button class="secondary" style="padding:0.25rem 0.75rem;margin-left:0.5rem;">Log out</button></form></small></p>
            <form method="post" action="/broadcast/send" enctype="multipart/form-data">
                <label for="channel">Channel</label>
                <input type="text" id="channel" name="channel_name" list="channel-options" placeholder="#announcements" autocomplete="off" required />
                <datalist id="channel-options">
                    {options}
                </datalist>
                <input type="hidden" id="channel_id" name="channel_id" />
                <label for="message">Message</label>
                <textarea id="message" name="message" placeholder="Type your announcement...&#10;Mentions: use #channel-name, @everyone, or @here."></textarea>
                <div class="checkbox">
                    <input type="checkbox" id="use_embed" name="use_embed" value="1" checked />
                    <label for="use_embed" style="margin:0;">Render using SPL Shield embed</label>
                </div>
                <label for="image">Image (optional)</label>
                <input type="file" id="image" name="image" accept="image/png,image/jpeg,image/webp,image/gif" />
                <div class="actions">
                    <button type="submit" class="primary">Send Broadcast</button>
                </div>
            </form>
            <script type="application/json" id="channel-data">{channel_json}</script>
            <script>
                (function() {{
                    const channelInput = document.getElementById("channel");
                    const channelIdInput = document.getElementById("channel_id");
                    const channels = JSON.parse(document.getElementById("channel-data").textContent);
                    function updateChannelId() {{
                        const value = channelInput.value.trim().replace(/^#/,'').toLowerCase();
                        const match = channels.find((c) => c.name.toLowerCase() === value);
                        channelIdInput.value = match ? match.id : "";
                    }}
                    channelInput.addEventListener("input", updateChannelId);
                    updateChannelId();
                }})();
            </script>
        </div>
    </body>
    </html>
    """.strip()
    return HTMLResponse(html)


@router.post("/send")
async def send_broadcast(
    request: Request,
    channel_id: str = Form(""),
    channel_name: str = Form(""),
    message: str = Form(""),
    use_embed: str = Form("0"),
    image: UploadFile | None = File(None),
) -> RedirectResponse:
    user = await _require_session_user(request)
    if not user:
        return RedirectResponse("/broadcast/login")
    if not settings.discord_bot_token:
        raise HTTPException(status_code=503, detail="Discord bot token missing.")

    channels = await _fetch_channels()
    lookup = {ch["name"].lower(): ch["id"] for ch in channels}
    resolved_channel_id = channel_id
    if not resolved_channel_id and channel_name:
        resolved_channel_id = lookup.get(channel_name.strip().lstrip("#").lower(), "")
    if not resolved_channel_id:
        raise HTTPException(status_code=400, detail="Select a valid channel from the list.")

    content = message or ""
    embed_flag = use_embed == "1"
    file_data = None
    filename = None
    mime_type = None
    if image is not None and image.filename:
        file_data = await image.read()
        if file_data:
            filename = image.filename
            mime_type = image.content_type or "application/octet-stream"
        else:
            file_data = None

    try:
        await _send_discord_message(
            channel_id=resolved_channel_id,
            text=content,
            file_bytes=file_data,
            filename=filename,
            mime_type=mime_type,
            use_embed=embed_flag,
            channel_lookup=lookup,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse("/broadcast?status=sent", status_code=303)


async def _send_discord_message(
    *,
    channel_id: str,
    text: str,
    file_bytes: bytes | None,
    filename: str | None,
    mime_type: str | None,
    use_embed: bool,
    channel_lookup: dict[str, str] | None = None,
) -> None:
    content = text.replace("\r\n", "\n").strip()
    if channel_lookup:
        content = _replace_channel_mentions(content, channel_lookup)
    if len(content) > 1900:
        raise ValueError("Message too long; please keep it below 1,900 characters.")
    if not content and file_bytes is None:
        raise ValueError("Provide a message or attach a file to broadcast.")

    payload: dict[str, Any] = {}
    embed_payload: dict[str, Any] | None = None
    if use_embed:
        embed = DiscordBotRunner._build_say_embed(content or "\u200b")
        embed_payload = embed.to_dict()
        payload["embeds"] = [embed_payload]
        if content:
            payload["content"] = content
    elif content:
        payload["content"] = content

    files = None
    if file_bytes is not None and filename:
        payload["attachments"] = [{"id": 0, "filename": filename}]
        if embed_payload and DiscordBotRunner._is_image_filename(filename):
            embed_payload.setdefault("image", {"url": f"attachment://{filename}"})
        files = [
            (
                "payload_json",
                (None, json.dumps(payload), "application/json"),
            ),
            (
                "files[0]",
                (filename, file_bytes, mime_type or "application/octet-stream"),
            ),
        ]
    async with httpx.AsyncClient(timeout=20) as client:
        if files:
            resp = await client.post(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {settings.discord_bot_token}"},
                files=files,
            )
        else:
            resp = await client.post(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers={
                    "Authorization": f"Bot {settings.discord_bot_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="Discord rejected the broadcast.")


def _replace_channel_mentions(text: str, channel_lookup: dict[str, str]) -> str:
    if not text:
        return text

    pattern = r"#([a-zA-Z0-9_\-]+)|(\\?@everyone)|(\\?@here)"

    def _sub(match: re.Match[str]) -> str:
        if match.group(1):
            name = match.group(1).lower()
            channel_id = channel_lookup.get(name)
            return f"<#{channel_id}>" if channel_id else match.group(0)
        if match.group(2):
            return "@everyone"
        if match.group(3):
            return "@here"
        return match.group(0)

    return re.sub(pattern, _sub, text)
