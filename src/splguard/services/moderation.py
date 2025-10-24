from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings as app_settings
from ..models import ModerationRule, Settings, UserInfraction

CACHE_TTL_SECONDS = 60
_PROFILE_CACHE: tuple[datetime, ModerationProfile] | None = None
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "warn": 1,
    "mute": 3,
    "ban": 5,
    "ttl_seconds": 6 * 60 * 60,
    "mute_seconds": 60 * 30,
}


@dataclass
class ModerationProfile:
    settings_id: int
    allowed_domains: set[str]
    probation_seconds: int
    media_probation_seconds: int
    max_mentions: int
    ad_keywords: list[str]
    thresholds: dict[str, int]
    strike_ttl: int
    mute_seconds: int
    admin_channel_id: Optional[int]


class ModerationAction:
    DELETE = "delete"
    WARN = "warn"
    MUTE = "mute"
    BAN = "ban"


@dataclass
class StrikeDecision:
    action: str
    strikes: int
    threshold: int
    reason: str
    acted_at: datetime


def _domain_from_url(url: str | None) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url if url.startswith(("http://", "https://")) else f"http://{url}")
    return parsed.hostname.lower() if parsed.hostname else None


class ModerationService:
    def __init__(self, session: AsyncSession, redis: Redis | None):
        self._session = session
        self._redis = redis

    async def get_profile(self) -> Optional[ModerationProfile]:
        global _PROFILE_CACHE
        now = datetime.now(timezone.utc)
        if _PROFILE_CACHE and now < _PROFILE_CACHE[0]:
            return _PROFILE_CACHE[1]

        query = (
            select(Settings)
            .options(selectinload(Settings.moderation_rules))
            .limit(1)
        )
        result = await self._session.execute(query)
        settings_row: Settings | None = result.scalar_one_or_none()
        if settings_row is None:
            return None

        rule: ModerationRule | None = (
            settings_row.moderation_rules[0] if settings_row.moderation_rules else None
        )

        thresholds = dict(DEFAULT_THRESHOLDS)
        if rule and rule.repeated_offense_thresholds:
            thresholds.update({k: int(v) for k, v in rule.repeated_offense_thresholds.items() if str(v).isdigit() or isinstance(v, int)})
            if "ttl_seconds" in rule.repeated_offense_thresholds:
                thresholds["ttl_seconds"] = int(rule.repeated_offense_thresholds["ttl_seconds"])
            if "mute_seconds" in rule.repeated_offense_thresholds:
                thresholds["mute_seconds"] = int(rule.repeated_offense_thresholds["mute_seconds"])

        allowed_domains = set(rule.allowed_domains or []) if rule else set()

        derived_urls = [
            settings_row.website,
            settings_row.docs,
            settings_row.explorer_url,
        ]
        for link in (settings_row.social_links or {}).values():
            derived_urls.append(link)

        for url in derived_urls:
            domain = _domain_from_url(url)
            if domain:
                allowed_domains.add(domain)

        allowed_domains = {domain.lower() for domain in allowed_domains}

        probation_seconds = rule.new_user_probation_duration if rule else 0
        profile = ModerationProfile(
            settings_id=settings_row.id,
            allowed_domains=allowed_domains,
            probation_seconds=probation_seconds,
            media_probation_seconds=probation_seconds,
            max_mentions=rule.max_mentions if rule else 5,
            ad_keywords=list(rule.ad_keywords or []) if rule else [],
            thresholds={
                "warn": thresholds.get("warn", DEFAULT_THRESHOLDS["warn"]),
                "mute": thresholds.get("mute", DEFAULT_THRESHOLDS["mute"]),
                "ban": thresholds.get("ban", DEFAULT_THRESHOLDS["ban"]),
            },
            strike_ttl=int(thresholds.get("ttl_seconds", DEFAULT_THRESHOLDS["ttl_seconds"])),
            mute_seconds=int(thresholds.get("mute_seconds", DEFAULT_THRESHOLDS["mute_seconds"])),
            admin_channel_id=app_settings.admin_channel_id or app_settings.owner_id,
        )

        _PROFILE_CACHE = (now + timedelta(seconds=CACHE_TTL_SECONDS), profile)
        return profile

    async def increment_strike(
        self,
        profile: ModerationProfile,
        user_id: int,
        chat_id: int,
        reason: str,
        username: str | None,
    ) -> StrikeDecision:
        acting_at = datetime.now(timezone.utc)
        redis_count = None
        if self._redis is not None:
            redis_key = f"strikes:{chat_id}:{user_id}"
            redis_count = await self._redis.incr(redis_key)
            await self._redis.expire(redis_key, profile.strike_ttl)

        stmt = (
            select(UserInfraction)
            .where(
                UserInfraction.settings_id == profile.settings_id,
                UserInfraction.telegram_user_id == user_id,
            )
            .limit(1)
        )
        db_result = await self._session.execute(stmt)
        record: UserInfraction | None = db_result.scalar_one_or_none()

        if record is None:
            record = UserInfraction(
                settings_id=profile.settings_id,
                telegram_user_id=user_id,
                username=username,
                strike_count=0,
            )
            self._session.add(record)

        if username:
            record.username = username
        record.strike_count += 1
        record.updated_at = acting_at
        record.is_muted = False

        await self._session.flush()

        strikes = redis_count if redis_count is not None else record.strike_count
        action = ModerationAction.DELETE
        threshold = profile.thresholds["warn"]

        if strikes >= profile.thresholds["ban"]:
            action = ModerationAction.BAN
            threshold = profile.thresholds["ban"]
            history = record.ban_history or []
            history.append({"timestamp": acting_at.isoformat(), "reason": reason})
            record.ban_history = history
            record.is_muted = False
        elif strikes >= profile.thresholds["mute"]:
            action = ModerationAction.MUTE
            threshold = profile.thresholds["mute"]
            record.is_muted = True
        elif strikes >= profile.thresholds["warn"]:
            action = ModerationAction.WARN
            threshold = profile.thresholds["warn"]

        await self._session.commit()

        return StrikeDecision(
            action=action,
            strikes=strikes,
            threshold=threshold,
            reason=reason,
            acted_at=acting_at,
        )

    async def _get_user_record(
        self, profile: ModerationProfile, user_id: int, create: bool = False, username: str | None = None
    ) -> UserInfraction | None:
        stmt = (
            select(UserInfraction)
            .where(
                UserInfraction.settings_id == profile.settings_id,
                UserInfraction.telegram_user_id == user_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is not None or not create:
            return record

        record = UserInfraction(
            settings_id=profile.settings_id,
            telegram_user_id=user_id,
            username=username,
            strike_count=0,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def is_trusted(self, profile: ModerationProfile, user_id: int) -> bool:
        if user_id == app_settings.owner_id or user_id in app_settings.admin_ids:
            return True
        record = await self._get_user_record(profile, user_id)
        if record is None:
            return False
        return record.is_admin or record.is_trusted

    async def is_admin(self, profile: ModerationProfile, user_id: int) -> bool:
        if user_id == app_settings.owner_id or user_id in app_settings.admin_ids:
            return True
        record = await self._get_user_record(profile, user_id)
        if record is None:
            return False
        return bool(record.is_admin)

    async def set_probation(
        self,
        profile: ModerationProfile,
        chat_id: int,
        user_id: int,
        username: str | None,
        probation_seconds: int,
    ) -> None:
        if probation_seconds <= 0:
            return
        record = await self._get_user_record(profile, user_id, create=True, username=username)
        now = datetime.now(timezone.utc)
        record.username = username or record.username
        if record.joined_at is None:
            record.joined_at = now
        record.probation_until = now + timedelta(seconds=probation_seconds)
        record.updated_at = now
        await self._session.commit()

        if self._redis is not None:
            key = f"probation:{chat_id}:{user_id}"
            await self._redis.set(key, "1", ex=probation_seconds)

    async def is_user_in_probation(
        self,
        profile: ModerationProfile,
        chat_id: int,
        user_id: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        record = await self._get_user_record(profile, user_id)
        # SQLite stores datetimes as naive, so we need to make them timezone-aware
        probation_until = record.probation_until.replace(tzinfo=timezone.utc) if record and record.probation_until and record.probation_until.tzinfo is None else record.probation_until if record else None
        if record and probation_until and probation_until > now:
            if self._redis is not None:
                ttl = int((probation_until - now).total_seconds())
                if ttl > 0:
                    await self._redis.set(f"probation:{chat_id}:{user_id}", "1", ex=ttl)
            return True

        if self._redis is not None:
            key = f"probation:{chat_id}:{user_id}"
            ttl = await self._redis.ttl(key)
            if ttl and ttl > 0:
                return True
        return False
