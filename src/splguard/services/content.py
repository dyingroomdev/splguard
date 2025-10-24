from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

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
            cached = await self._redis.get(key)
            if cached:
                return json.loads(cached)

        result = await loader()

        if self._redis is not None and result is not None:
            await self._redis.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)

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
        settings: Settings | None = result.scalar_one_or_none()
        if settings is None:
            return None

        presale_payload = None
        if settings.presales:
            fallback_start = datetime.min.replace(tzinfo=timezone.utc)
            presale = sorted(
                settings.presales,
                key=lambda p: (
                    (p.start_time or fallback_start),
                    p.id,
                ),
            )[0]
            presale_payload = self._serialize_presale(presale)

        return {
            "project_name": settings.project_name,
            "token_ticker": settings.token_ticker,
            "contract_addresses": list(settings.contract_addresses or []),
            "explorer_url": settings.explorer_url,
            "website": settings.website,
            "docs": settings.docs,
            "social_links": settings.social_links or {},
            "logo": settings.logo,
            "team": [self._serialize_team_member(member) for member in sorted(
                settings.team_members, key=lambda member: (member.display_order, member.id)
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
