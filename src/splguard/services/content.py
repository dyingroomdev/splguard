from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings as app_settings
from ..models import Presale, Settings, TeamMember

CACHE_TTL_SECONDS = 60


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    return format(normalized, "f")


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


class ContentService:
    def __init__(self, session: AsyncSession, redis: Redis | None):
        self._session = session
        self._redis = redis

    async def _get_cached(self, key: str, loader: Callable[[], Any]) -> Any:
        if self._redis is not None:
            try:
                cached = await self._redis.get(key)
            except RedisError:
                cached = None
            if cached:
                return json.loads(cached)

        result = await loader()

        if self._redis is not None and result is not None:
            try:
                await self._redis.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)
            except RedisError:
                pass

        return result

    async def get_settings_payload(self) -> dict[str, Any] | None:
        return await self._get_cached("content:settings", self._load_settings_payload)

    async def _load_settings_payload(self) -> dict[str, Any] | None:
        query = (
            select(Settings)
            .options(
                selectinload(Settings.team_members),
                selectinload(Settings.presales),
            )
            .limit(1)
        )
        result = await self._session.execute(query)
        settings_row: Settings | None = result.scalar_one_or_none()
        if settings_row is None:
            return None

        presale_payload = None
        if settings_row.presales:
            fallback_start = datetime.min.replace(tzinfo=timezone.utc)
            presale = sorted(
                settings_row.presales,
                key=lambda p: (
                    (p.start_time or fallback_start),
                    p.id,
                ),
            )[0]
            presale_payload = self._serialize_presale(presale)

        return {
            "project_name": settings_row.project_name,
            "token_ticker": settings_row.token_ticker,
            "contract_addresses": list(settings_row.contract_addresses or []),
            "explorer_url": settings_row.explorer_url,
            "website": settings_row.website,
            "docs": settings_row.docs,
            "social_links": settings_row.social_links or {},
            "logo": settings_row.logo,
            "supply_display": app_settings.tdl_supply_display,
            "token_mint": app_settings.tdl_mint,
            "team": [self._serialize_team_member(member) for member in sorted(
                settings_row.team_members, key=lambda member: (member.display_order, member.id)
            )],
            "presale": presale_payload,
        }

    @staticmethod
    def _serialize_team_member(member: TeamMember) -> dict[str, Any]:
        return {
            "name": member.name,
            "role": member.role,
            "contact": member.contact,
            "avatar_url": member.avatar_url,
            "bio": member.bio,
            "display_order": member.display_order,
        }

    @staticmethod
    def _serialize_presale(presale: Presale) -> dict[str, Any]:
        return {
            "status": presale.status.value,
            "platform": presale.platform,
            "links": presale.links or {},
            "hardcap": _serialize_decimal(presale.hardcap),
            "softcap": _serialize_decimal(presale.softcap),
            "start_time": _serialize_datetime(presale.start_time),
            "end_time": _serialize_datetime(presale.end_time),
            "raised_so_far": _serialize_decimal(presale.raised_so_far),
            "faqs": presale.faqs or [],
        }
