from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import Presale, PresaleStatus, Settings
from ..templates import render_presale_block
logger = logging.getLogger(__name__)

SUMMARY_CACHE_KEY = "presale:summary"
WATCHERS_SET_KEY = "presale:watchers"
PINNED_KEY_TEMPLATE = "presale:pinned:{chat_id}"


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    quantized = value.normalize()
    return format(quantized, "f")


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


@dataclass(slots=True)
class PresaleSummary:
    project_name: str
    status: str
    platform: str | None
    links: dict[str, str]
    hardcap: str | None
    softcap: str | None
    raised_so_far: str | None
    start_time: str | None
    end_time: str | None
    faqs: list[dict[str, Any]]
    updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "status": self.status,
            "platform": self.platform,
            "links": self.links,
            "hardcap": self.hardcap,
            "softcap": self.softcap,
            "raised_so_far": self.raised_so_far,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "faqs": self.faqs,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        return render_presale_block(
            status=self.status,
            project_name=self.project_name,
            platform=self.platform,
            link=self.primary_link,
            hardcap=self.hardcap,
            softcap=self.softcap,
            raised=self.raised_so_far,
            start_time=self.start_time,
            end_time=self.end_time,
        )

    @property
    def primary_link(self) -> str | None:
        if not self.links:
            return None
        preferred_keys = ["primary", "url", "link", "sale", "pinksale"]
        for key in preferred_keys:
            value = self.links.get(key)
            if value:
                return value
        # Fallback to first value
        for value in self.links.values():
            if value:
                return value
        return None


class PresaleService:
    def __init__(self, session: AsyncSession, redis: Redis | None):
        self._session = session
        self._redis = redis

    async def get_summary(self, refresh_external: bool = True) -> PresaleSummary | None:
        settings_row, presale = await self._load_presale()
        if settings_row is None or presale is None:
            return None

        if refresh_external:
            await self._maybe_sync_with_external(presale)
            await self._session.refresh(presale)

        return self._to_summary(settings_row.project_name, presale)

    async def _load_presale(self) -> tuple[Settings | None, Presale | None]:
        try:
            settings_stmt = select(Settings).options(selectinload(Settings.presales)).limit(1)
            settings_result = await self._session.execute(settings_stmt)
            settings_row: Settings | None = settings_result.scalar_one_or_none()
            if settings_row is None:
                return None, None

            if settings_row.presales:
                fallback = datetime.min.replace(tzinfo=timezone.utc)
                presale = sorted(
                    settings_row.presales,
                    key=lambda p: (p.start_time or fallback, p.id),
                )[0]
                return settings_row, presale

            presale = Presale(settings_id=settings_row.id)
            self._session.add(presale)
            await self._session.flush()
            return settings_row, presale
        except ProgrammingError as exc:
            logger.debug("Database tables not initialized yet: %s", exc)
            return None, None

    async def update_presale(self, **fields: Any) -> PresaleSummary | None:
        settings_row, presale = await self._load_presale()
        if settings_row is None or presale is None:
            return None

        for key, value in fields.items():
            if hasattr(presale, key):
                setattr(presale, key, value)

        await self._session.commit()
        await self.invalidate_caches()
        return await self.get_summary(refresh_external=False)

    async def _maybe_sync_with_external(self, presale: Presale) -> None:
        api_url = settings.presale_api_url
        if not api_url:
            return

        payload = await self._fetch_external(api_url)
        if not payload:
            return

        changed = False

        status = payload.get("status")
        if status and status.lower() in {item.value for item in PresaleStatus}:
            new_status = PresaleStatus(status.lower())
            if presale.status != new_status:
                presale.status = new_status
                changed = True

        for attribute in ("platform",):
            value = payload.get(attribute)
            if value and getattr(presale, attribute) != value:
                setattr(presale, attribute, value)
                changed = True

        numeric_fields = {
            "hardcap": payload.get("hardcap"),
            "softcap": payload.get("softcap"),
            "raised_so_far": payload.get("raised"),
        }
        for field, value in numeric_fields.items():
            if value is None:
                continue
            try:
                decimal_value = Decimal(str(value))
            except Exception:
                logger.debug("Skipping invalid numeric value for %s: %s", field, value)
                continue
            if getattr(presale, field) != decimal_value:
                setattr(presale, field, decimal_value)
                changed = True

        time_fields = {
            "start_time": payload.get("start_time"),
            "end_time": payload.get("end_time"),
        }
        for field, value in time_fields.items():
            if not value:
                continue
            try:
                parsed = self._parse_datetime(value)
            except ValueError:
                logger.debug("Invalid datetime from API for %s: %s", field, value)
                continue
            if getattr(presale, field) != parsed:
                setattr(presale, field, parsed)
                changed = True

        links = payload.get("links")
        if isinstance(links, dict) and links != presale.links:
            presale.links = links
            changed = True

        if changed:
            await self._session.commit()
            await self.invalidate_caches()

    async def _fetch_external(self, url: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning("Failed to refresh presale data from API: %s", exc)
            return None

    async def invalidate_caches(self) -> None:
        if self._redis is None:
            return
        await self._redis.delete(SUMMARY_CACHE_KEY)
        await self._redis.delete("content:settings")

    def _to_summary(self, project_name: str, presale: Presale) -> PresaleSummary:
        return PresaleSummary(
            project_name=project_name,
            status=presale.status.value,
            platform=presale.platform,
            links=presale.links or {},
            hardcap=_decimal_to_str(presale.hardcap),
            softcap=_decimal_to_str(presale.softcap),
            raised_so_far=_decimal_to_str(presale.raised_so_far),
            start_time=_dt_to_iso(presale.start_time),
            end_time=_dt_to_iso(presale.end_time),
            faqs=presale.faqs or [],
            updated_at=_dt_to_iso(presale.updated_at),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)

    async def add_watcher(self, chat_id: int) -> None:
        if self._redis is None:
            return
        await self._redis.sadd(WATCHERS_SET_KEY, str(chat_id))

    async def watchers(self) -> set[int]:
        if self._redis is None:
            return set()
        members = await self._redis.smembers(WATCHERS_SET_KEY)
        return {int(member) for member in members if member}

    async def get_cached_summary(self) -> PresaleSummary | None:
        if self._redis is None:
            return None
        raw = await self._redis.get(SUMMARY_CACHE_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return PresaleSummary(**data)

    async def cache_summary(self, summary: PresaleSummary) -> None:
        if self._redis is None:
            return
        await self._redis.set(SUMMARY_CACHE_KEY, json.dumps(summary.to_dict()))

    async def set_pinned_message(self, chat_id: int, message_id: int) -> None:
        if self._redis is None:
            return
        await self._redis.set(PINNED_KEY_TEMPLATE.format(chat_id=chat_id), str(message_id))

    async def get_pinned_message(self, chat_id: int) -> int | None:
        if self._redis is None:
            return None
        raw = await self._redis.get(PINNED_KEY_TEMPLATE.format(chat_id=chat_id))
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
