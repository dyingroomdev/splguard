from __future__ import annotations

import logging
import html

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import httpx
import json
import random
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..metrics import increment as metrics_increment, set_value as metrics_set
from ..db import AsyncSessionMaker
from ..models import (
    ZealyGrant,
    ZealyGrantStatus,
    ZealyMember,
    ZealyQuest,
)
from ..redis import get_redis_client

logger = logging.getLogger(__name__)


class ZealyNotConfiguredError(RuntimeError):
    """Raised when Zealy integration is not fully configured."""


def _ensure_configured() -> None:
    if not (
        settings.zealy_enabled
        and settings.zealy_api_key
        and settings.zealy_community_id
    ):
        raise ZealyNotConfiguredError("Zealy integration is not enabled or configured.")


TIER_RULES: list[tuple[str, int]] = [
    ("elite", 3000),
    ("alpha", 1500),
    ("wl", 500),
    ("member", 0),
]

TIER_LABELS = {
    "member": "Member",
    "wl": "Whitelist",
    "alpha": "Alpha",
    "elite": "Elite",
}

TIER_ALIASES = {
    "whitelist": "wl",
}

TIER_PRIVILEGES = {
    "member": [
        "Access public commands",
        "Participate in community chat",
    ],
    "wl": [
        "Priority support",
        "Submit presale transactions",
    ],
    "alpha": [
        "Beta features access",
        "Vote on roadmap items",
    ],
    "elite": [
        "Direct line to core team",
        "Early access to partnerships",
    ],
}
TIER_PRIVILEGES["whitelist"] = TIER_PRIVILEGES["wl"]


def tier_rank(tier: str | None) -> int:
    tier_key = (tier or "member").lower()
    tier_key = TIER_ALIASES.get(tier_key, tier_key)
    for rank, (name, _) in enumerate(reversed(TIER_RULES)):
        if name == tier_key:
            return rank
    return 0


def determine_tier(xp: int) -> str:
    for name, threshold in TIER_RULES:
        if xp >= threshold:
            return name
    return "member"


def tier_label(tier: str | None) -> str:
    if not tier:
        return TIER_LABELS["member"]
    tier_key = TIER_ALIASES.get(tier.lower(), tier.lower())
    return TIER_LABELS.get(tier_key, tier.title())


def tier_privileges(tier: str | None) -> list[str]:
    tier_key = (tier or "member").lower()
    tier_key = TIER_ALIASES.get(tier_key, tier_key)
    if tier_key not in TIER_PRIVILEGES:
        tier_key = "member"
    return TIER_PRIVILEGES[tier_key]


def calculate_level(xp: int) -> int:
    return max(1, (xp // 250) + 1)


@dataclass(slots=True)
class GrantResult:
    grant: ZealyGrant
    tier_changed: bool
    previous_tier: str | None
    new_tier: str | None
    level_changed: bool
    previous_level: int
    new_level: int


DLQ_KEY = "zealy:dlq"
_bot_instance: Bot | None = None


def _get_bot() -> Bot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=None),
        )
    return _bot_instance


@dataclass(slots=True)
class ZealyClient:
    api_key: str
    base_url: str

    async def post(self, path: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        request_payload = dict(payload or {})
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post(path, json=request_payload, headers=headers)
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}


def _client() -> ZealyClient:
    _ensure_configured()
    base_url = (settings.zealy_base_url or "https://api.zealy.io").rstrip("/")
    return ZealyClient(api_key=settings.zealy_api_key, base_url=base_url)


async def complete_quest(quest_id: str, user_id: str | None = None) -> Mapping[str, Any]:
    """Mark a quest as completed for a user."""
    client = _client()
    community_id = settings.zealy_community_id
    payload: dict[str, Any] = {}
    if user_id:
        payload["userId"] = user_id
    path = f"/communities/{community_id}/quests/{quest_id}/complete"
    return await client.post(path, payload)


async def grant_xp(user_id: str, amount: int) -> Mapping[str, Any]:
    """Grant XP to a user inside the Zealy community."""
    if amount <= 0:
        raise ValueError("XP amount must be a positive integer.")
    client = _client()
    community_id = settings.zealy_community_id
    path = f"/communities/{community_id}/users/{user_id}/xp"
    payload = {"amount": amount}
    return await client.post(path, payload)


async def process_event(event: str, payload: Mapping[str, Any]) -> bool:
    """Process inbound webhook events from Zealy."""
    normalized = (event or "").lower()

    if normalized in {"quest.claimed", "quest.succeeded", "quest.failed"}:
        quest_id = str(payload.get("questId") or payload.get("quest_id") or "")
        user_id = str(payload.get("userId") or payload.get("user_id") or "")
        logger.info(
            "zealy_quest_event",
            extra={
                "event": normalized,
                "quest_id": quest_id,
                "user_id": user_id,
            },
        )
        if normalized == "quest.succeeded":
            xp = payload.get("xp") or payload.get("xpEarned") or payload.get("xp_earned")
            try:
                xp_value = int(xp) if xp is not None else None
            except (TypeError, ValueError):
                xp_value = None

            if xp_value and xp_value > 0 and settings.zealy_enabled and user_id:
                try:
                    await grant_xp(user_id=user_id, amount=xp_value)
                except ZealyNotConfiguredError:
                    logger.debug("Zealy integration disabled while handling quest success.")
                except Exception:  # pragma: no cover - network failures are logged only
                    logger.exception("Failed to grant Zealy XP for quest success.")
        return True

    if normalized in {"user.joined", "user.left"}:
        user_id = str(payload.get("userId") or payload.get("user_id") or "")
        logger.info(
            "zealy_user_event",
            extra={
                "event": normalized,
                "user_id": user_id,
            },
        )
        return True

    logger.debug("Unsupported Zealy event received: %s", normalized)
    return False


def _normalize_wallet(wallet: str) -> str:
    normalized = wallet.strip()
    if not normalized:
        raise ValueError("Wallet address cannot be empty.")
    if len(normalized) < 32 or len(normalized) > 64:
        raise ValueError("Wallet address must be between 32 and 64 characters.")
    if any(ch.isspace() for ch in normalized):
        raise ValueError("Wallet address cannot contain whitespace.")
    if not normalized.isalnum():
        raise ValueError("Wallet address must be alphanumeric.")
    return normalized


async def get_member(session: AsyncSession, telegram_id: int) -> ZealyMember | None:
    result = await session.execute(
        select(ZealyMember).where(ZealyMember.telegram_id == telegram_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_member_by_zealy_id(session: AsyncSession, zealy_user_id: str | None) -> ZealyMember | None:
    if not zealy_user_id:
        return None
    result = await session.execute(
        select(ZealyMember).where(ZealyMember.zealy_user_id == zealy_user_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_member(session: AsyncSession, telegram_id: int) -> tuple[ZealyMember, bool]:
    member = await get_member(session, telegram_id)
    if member:
        return member, False

    member = ZealyMember(telegram_id=telegram_id, metadata={})
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member, True


async def bind_wallet(
    session: AsyncSession,
    telegram_id: int,
    wallet: str,
) -> tuple[ZealyMember, str]:
    """Bind a wallet address to the Zealy member belonging to the Telegram user."""
    wallet_normalized = _normalize_wallet(wallet)

    result = await session.execute(
        select(ZealyMember).where(
            ZealyMember.wallet == wallet_normalized,
            ZealyMember.telegram_id != telegram_id,
        )
    )
    conflict = result.scalar_one_or_none()
    if conflict:
        raise ValueError("That wallet is already linked to another member.")

    member, created = await get_or_create_member(session, telegram_id)
    if member.wallet == wallet_normalized:
        return member, "unchanged"

    member.wallet = wallet_normalized
    await session.commit()
    await session.refresh(member)
    return member, "created" if created else "linked"


async def list_active_quests(
    session: AsyncSession,
    limit: int = 10,
) -> Sequence[ZealyQuest]:
    stmt = (
        select(ZealyQuest)
        .order_by(ZealyQuest.updated_at.desc(), ZealyQuest.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_member_summary(
    session: AsyncSession,
    telegram_id: int,
    recent_limit: int = 5,
) -> dict[str, Any] | None:
    member = await get_member(session, telegram_id)
    if member is None:
        return None

    grants_stmt = (
        select(ZealyGrant)
        .where(ZealyGrant.member_id == member.id)
        .order_by(ZealyGrant.created_at.desc())
        .limit(recent_limit)
        .options(selectinload(ZealyGrant.quest))
    )
    grant_result = await session.execute(grants_stmt)
    grants = grant_result.scalars().all()

    recent_rewards = []
    for grant in grants:
        quest_slug = grant.quest.slug if grant.quest else None
        reward = {
            "quest": quest_slug,
            "status": grant.status.value,
            "xp": grant.xp_awarded if grant.xp_awarded is not None else (
                grant.quest.xp_value if grant.quest else None
            ),
            "tx_ref": grant.tx_ref,
            "created_at": grant.created_at.isoformat() if isinstance(grant.created_at, datetime) else None,
        }
        recent_rewards.append(reward)

    return {
        "member": member,
        "wallet": member.wallet,
        "xp": member.xp or 0,
        "level": member.level or calculate_level(member.xp or 0),
        "tier": member.tier,
        "tier_label": tier_label(member.tier),
        "privileges": tier_privileges(member.tier),
        "recent_rewards": recent_rewards,
    }


async def get_or_create_quest(
    session: AsyncSession,
    slug: str,
    xp_value: int = 0,
    zealy_quest_id: str | None = None,
) -> ZealyQuest:
    stmt = select(ZealyQuest).where(ZealyQuest.slug == slug).limit(1)
    result = await session.execute(stmt)
    quest = result.scalar_one_or_none()
    if quest:
        return quest

    quest = ZealyQuest(
        slug=slug,
        xp_value=xp_value,
        zealy_quest_id=zealy_quest_id,
        metadata={},
    )
    session.add(quest)
    await session.commit()
    await session.refresh(quest)
    return quest


async def record_grant(
    session: AsyncSession,
    member: ZealyMember,
    quest: ZealyQuest,
    status: ZealyGrantStatus,
    tx_ref: str,
    xp_awarded: int | None = None,
) -> GrantResult:
    grant = ZealyGrant(
        member_id=member.id,
        quest_id=quest.id,
        status=status,
        tx_ref=tx_ref,
        xp_awarded=xp_awarded if xp_awarded is not None else quest.xp_value,
        metadata={},
    )
    session.add(grant)
    previous_tier = member.tier
    previous_level = member.level or calculate_level(member.xp or 0)

    if grant.xp_awarded:
        member.xp = (member.xp or 0) + int(grant.xp_awarded)

    member.level = calculate_level(member.xp or 0)
    member.tier = determine_tier(member.xp or 0)
    previous_tier_normalized = previous_tier or "member"
    new_tier_normalized = member.tier or "member"
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("duplicate_grant") from exc
    await session.refresh(grant)
    await session.refresh(member)
    tier_changed = previous_tier_normalized != new_tier_normalized
    if previous_tier is None and new_tier_normalized == "member":
        tier_changed = False

    metrics_increment("zealy_awards_total")

    return GrantResult(
        grant=grant,
        tier_changed=tier_changed,
        previous_tier=previous_tier,
        new_tier=member.tier,
        level_changed=member.level != previous_level,
        previous_level=previous_level,
        new_level=member.level,
    )


async def process_event(
    event: str,
    payload: Mapping[str, Any],
    session: AsyncSession | None = None,
    bot: Bot | None = None,
    redis: Redis | None = None,
) -> bool:
    metrics_increment("zealy_events_total")
    normalized = (event or "").lower()
    redis = redis or get_redis_client()

    if session is None:
        async with AsyncSessionMaker() as session_obj:
            return await _process_event(normalized, payload, session_obj, bot, redis)
    return await _process_event(normalized, payload, session, bot, redis)


async def _process_event(
    event: str,
    payload: Mapping[str, Any],
    session: AsyncSession,
    bot: Bot | None,
    redis: Redis | None,
) -> bool:
    dedupe_key = _dedupe_key(event, payload)
    if dedupe_key and redis is not None:
        stored = await redis.set(f"zealy:event:{dedupe_key}", "1", ex=30, nx=True)
        if stored is None:
            return True

    if event in {"quest.claimed", "quest.succeeded", "quest.failed"}:
        await _handle_quest_event(event, payload, session, bot)
        return True

    if event in {"user.joined", "user.left"}:
        await _handle_member_lifecycle(event, payload, session, bot)
        return True

    if event in {"sprint.started", "sprint.ended"}:
        await _handle_sprint_event(event, payload, bot)
        return True

    logger.debug("Unsupported Zealy event received: %s", event)
    return False


def _dedupe_key(event: str, payload: Mapping[str, Any]) -> str | None:
    return (
        str(payload.get("eventId"))
        or str(payload.get("id"))
        or f"{event}:{payload.get('userId')}:{payload.get('questId')}"
    )


async def _handle_quest_event(
    event: str,
    payload: Mapping[str, Any],
    session: AsyncSession,
    bot: Bot | None,
) -> None:
    member = await _resolve_member(session, payload)
    if not member or not member.telegram_id:
        return

    messages = {
        "quest.claimed": "Quest received – awaiting review.",
        "quest.succeeded": "🏅 Quest completed — XP awarded.",
        "quest.failed": "⚠️ Quest failed — try again.",
    }
    text = messages.get(event)
    if not text:
        return

    bot = bot or _get_bot()
    try:
        await bot.send_message(chat_id=member.telegram_id, text=text)
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to send quest event DM to %s: %s", member.telegram_id, exc)


async def _handle_member_lifecycle(
    event: str,
    payload: Mapping[str, Any],
    session: AsyncSession,
    bot: Bot | None,
) -> None:
    member = await _resolve_member(session, payload)
    if not member or not member.telegram_id:
        return

    text = (
        "👋 Welcome to the sprint! Let us know if you need help."
        if event == "user.joined"
        else "Goodbye! Come back anytime when you're ready to continue the sprint."
    )
    bot = bot or _get_bot()
    try:
        await bot.send_message(chat_id=member.telegram_id, text=text)
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to send lifecycle DM to %s: %s", member.telegram_id, exc)


async def _handle_sprint_event(
    event: str,
    payload: Mapping[str, Any],
    bot: Bot | None,
) -> None:
    channel_id = settings.admin_channel_id or settings.owner_id
    if channel_id is None:
        return

    name = payload.get("name") or payload.get("sprintName") or "Sprint"
    leaderboard = payload.get("leaderboard") or []
    lines = []
    if event == "sprint.started":
        lines.append(f"🚀 Sprint <b>{html.escape(str(name))}</b> has started!")
    else:
        lines.append(f"✅ Sprint <b>{html.escape(str(name))}</b> has ended!")

    if leaderboard:
        lines.append("")
        lines.append("🏆 <b>Leaderboard</b>")
        for index, entry in enumerate(leaderboard[:5], start=1):
            user = entry.get("user") or entry.get("username") or "Participant"
            xp = entry.get("xp") or entry.get("score") or entry.get("points")
            if xp is None:
                lines.append(f"{index}. {html.escape(str(user))}")
            else:
                lines.append(f"{index}. {html.escape(str(user))} — {xp} XP")

    bot = bot or _get_bot()
    try:
        await bot.send_message(
            chat_id=channel_id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to broadcast sprint event to %s: %s", channel_id, exc)


async def _resolve_member(session: AsyncSession, payload: Mapping[str, Any]) -> ZealyMember | None:
    zealy_user_id = str(payload.get("userId") or payload.get("user_id") or "") or None
    member = await get_member_by_zealy_id(session, zealy_user_id)

    if member is None:
        telegram_id = payload.get("telegramId") or payload.get("telegram_id")
        if telegram_id:
            try:
                telegram_id_int = int(telegram_id)
            except (TypeError, ValueError):
                telegram_id_int = None
            if telegram_id_int is not None:
                member = await get_member(session, telegram_id_int)
                if member and zealy_user_id and member.zealy_user_id != zealy_user_id:
                    member.zealy_user_id = zealy_user_id
                    await session.commit()

    if member is None and zealy_user_id:
        wallet = payload.get("wallet") or payload.get("walletAddress")
        if wallet:
            result = await session.execute(
                select(ZealyMember).where(ZealyMember.wallet == wallet).limit(1)
            )
            member = result.scalar_one_or_none()
            if member and member.zealy_user_id != zealy_user_id:
                member.zealy_user_id = zealy_user_id
                await session.commit()

    return member


async def enqueue_dlq(redis: Redis | None, item: Mapping[str, Any], max_len: int = 100) -> None:
    if redis is None:
        return
    await redis.lpush(DLQ_KEY, json.dumps(item))
    await redis.ltrim(DLQ_KEY, 0, max_len - 1)
    size = await redis.llen(DLQ_KEY)
    metrics_set("zealy_dlq_size", int(size))


async def dlq_snapshot(redis: Redis | None, limit: int = 5) -> dict[str, Any]:
    if redis is None:
        return {"size": 0, "entries": []}
    size = await redis.llen(DLQ_KEY)
    entries_raw = await redis.lrange(DLQ_KEY, 0, limit - 1)
    entries = []
    for raw in entries_raw:
        try:
            entries.append(json.loads(raw))
        except (TypeError, ValueError):
            continue
    metrics_set("zealy_dlq_size", int(size))
    return {"size": int(size), "entries": entries}
