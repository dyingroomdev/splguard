from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from redis.asyncio import Redis

from ..config import settings
from ..db import AsyncSessionMaker
from ..redis import get_redis_client
from ..services.presale import PresaleService, PresaleSummary

logger = logging.getLogger(__name__)


class PresaleMonitor:
    def __init__(self, interval_seconds: int | None = None):
        self._interval = interval_seconds or settings.presale_refresh_seconds or 60
        self._task: asyncio.Task | None = None
        self._redis: Redis | None = None
        self._stopped = asyncio.Event()

    async def start(self, bot) -> None:
        self._redis = get_redis_client()
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(bot))
        logger.info("Presale monitor started with interval %ss", self._interval)

    async def stop(self, *_args, **_kwargs) -> None:
        if self._task is None:
            return
        self._stopped.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        logger.info("Presale monitor stopped")

    async def _run(self, bot) -> None:
        while not self._stopped.is_set():
            try:
                await self._refresh(bot)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error during presale refresh")

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    async def _refresh(self, bot) -> None:
        async with AsyncSessionMaker() as session:
            service = PresaleService(session, self._redis)
            summary = await service.get_summary(refresh_external=True)
            if summary is None:
                return

            cached = await service.get_cached_summary()
            if cached and cached.to_dict() == summary.to_dict():
                return

            await service.cache_summary(summary)
            await self._update_watchers(bot, service, summary)

    async def _update_watchers(self, bot, service: PresaleService, summary: PresaleSummary) -> None:
        watchers = await service.watchers()
        if not watchers:
            return

        text = summary.to_markdown()

        for chat_id in watchers:
            try:
                previous_message_id = await service.get_pinned_message(chat_id)
                if previous_message_id:
                    with suppress(TelegramBadRequest, TelegramForbiddenError):
                        await bot.unpin_chat_message(chat_id=chat_id, message_id=previous_message_id)

                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
                with suppress(TelegramBadRequest, TelegramForbiddenError):
                    await bot.pin_chat_message(
                        chat_id=chat_id,
                        message_id=sent.message_id,
                        disable_notification=True,
                    )
                await service.set_pinned_message(chat_id, sent.message_id)
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                logger.debug("Failed updating presale summary in %s: %s", chat_id, exc)
            except Exception:
                logger.exception("Error while updating presale message for chat %s", chat_id)
