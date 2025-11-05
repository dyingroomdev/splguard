from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping

from ..utils import markdown as md
from .style import (
    BRAND_HEADER_EMOJI,
    CHAIN_EMOJI,
    CONTACT_EMOJI,
    DEFAULT_CHAIN_EMOJI,
    DEFAULT_ROLE_EMOJI,
    LINK_EMOJI,
    MAX_LINE_LENGTH,
    ROLE_EMOJI,
    STATUS_EMOJI,
    TEAM_MEMBER_EMOJI,
)


def _format_line(text: str) -> str:
    if len(text) <= MAX_LINE_LENGTH:
        return text
    return text[: MAX_LINE_LENGTH - 1] + "…"


def _role_badge(role: str | None) -> str:
    if not role:
        return ""
    emoji = ROLE_EMOJI.get(role.lower(), DEFAULT_ROLE_EMOJI)
    return f"{emoji} {md.escape_md(role)}"


def render_team_cards(members: Iterable[Mapping[str, str | int | None]]) -> str:
    lines: list[str] = [md.bold(f"{BRAND_HEADER_EMOJI} SPL Shield Core Team"), ""]
    for member in members:
        name = md.bold(md.escape_md(str(member.get("name", "Unknown"))))
        role = _role_badge(member.get("role"))
        contact = member.get("contact")
        bio = member.get("bio")

        lines.append(_format_line(f"{TEAM_MEMBER_EMOJI} {name}"))
        if role:
            lines.append(_format_line(f"   {role}"))
        if bio:
            lines.append(_format_line(f"   {md.escape_md(str(bio))}"))
        if contact:
            lines.append(_format_line(f"   {CONTACT_EMOJI} {md.escape_md(str(contact))}"))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()

    # Add footer
    lines.append("")
    lines.append(md.escape_md("💠 Together, they lead SPL Shield — the AI-powered Solana Risk Scanner and home of $TDL, our ecosystem utility token powering risk analysis, staking, and governance."))

    return md.join_lines(lines)


def render_contract_block(
    addresses: Iterable[str],
    chain: str | None = None,
    token_ticker: str | None = None,
    supply: str | None = None,
    explorer_url: str | None = None,
) -> str:
    chain_name = chain or "Solana"
    chain_key = chain_name.lower()
    chain_emoji = CHAIN_EMOJI.get(chain_key, DEFAULT_CHAIN_EMOJI)
    lines: list[str] = [
        md.bold(f"{BRAND_HEADER_EMOJI} Token Contract"),
        f"Chain: {chain_emoji} {md.escape_md(chain_name.title())}",
    ]

    if token_ticker:
        lines.append(f"Ticker: {md.inline_code(token_ticker)}")
    if supply:
        lines.append(f"Supply: {md.inline_code(supply)}")

    for idx, address in enumerate(addresses, start=1):
        lines.append(f"{idx}\\) {md.inline_code(address)}")

    if explorer_url:
        lines.append(f"{LINK_EMOJI} Explorer: {md.link('Open', explorer_url)}")

    return md.join_lines(_format_line(line) for line in lines)


def render_presale_block(
    status: str,
    project_name: str | None = None,
    platform: str | None = None,
    link: str | None = None,
    hardcap: str | None = None,
    softcap: str | None = None,
    raised: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    status_key = status.lower()
    status_label = f"{STATUS_EMOJI.get(status_key, '🟣')} {status_key.title()}"
    # Always show $TDL Presale as the heading
    heading = f"{BRAND_HEADER_EMOJI} {md.escape_md('$TDL Presale')}"
    lines: list[str] = [
        md.bold(heading),
        f"Status: {md.escape_md(status_label)}",
    ]
    if platform:
        lines.append(f"Platform: {md.escape_md(platform)}")
    if hardcap:
        lines.append(f"Hardcap: {md.inline_code(hardcap)}")
    if softcap:
        lines.append(f"Softcap: {md.inline_code(softcap)}")
    if raised:
        lines.append(f"Raised: {md.inline_code(raised)}")

    date_line = _format_date_range(start_time, end_time)
    if date_line:
        lines.append(date_line)

    if link:
        lines.append(f"{LINK_EMOJI} {md.link('View Presale', link)}")

    return md.join_lines(_format_line(line) for line in lines)


def _format_date_range(start: str | None, end: str | None) -> str | None:
    if not start and not end:
        return None
    formatted = []
    for value, label in ((start, "Start"), (end, "End")):
        if value:
            formatted.append(f"{label}: {md.inline_code(_format_datetime(value))}")
    if formatted:
        return " ".join(formatted)
    return None


def _format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_links_block(links: Mapping[str, str]) -> str:
    lines = [md.bold(f"{BRAND_HEADER_EMOJI} Official Links"), ""]
    for name, url in links.items():
        if not url:
            continue
        friendly = name.replace("_", " ").title()
        lines.append(_format_line(f"{LINK_EMOJI} {md.escape_md(friendly)}: {md.link('Open', url)}"))
    return md.join_lines(lines)


def render_quick_replies() -> str:
    replies = {
        "How to buy": (
            "Use trusted DEX links only and double-check the contract address."
        ),
        "Slippage tips": "Start at 0.5% and only increase if the swap fails.",
        "Official links": "All real links are shared via /links; anything else is a scam.",
        "Impostor warning": "Admins will never DM you first or ask for your seed phrase.",
    }
    lines = [md.bold(f"{BRAND_HEADER_EMOJI} Quick Replies"), ""]
    for title, body in replies.items():
        lines.append(f"{md.bold(md.escape_md(title))}: {md.escape_md(body)}")
    return md.join_lines(lines)
