from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, TYPE_CHECKING

from aiogram import BaseMiddleware
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatPermissions, Message
from redis.asyncio import Redis

from ..config import settings
from ..db import AsyncSessionMaker
from ..redis import get_redis_client
from ..metrics import increment as metrics_increment
from ..services.moderation import ModerationAction, ModerationService
from ..utils import markdown as md
from ..utils.detection import (
    ad_keyword_score,
    contains_media,
    count_mentions,
    domain_in_allowlist,
    extract_links,
)

Handler = Callable[[Any, Dict[str, Any]], Awaitable[Any]]
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker=AsyncSessionMaker):
        self._sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: Any, data: Dict[str, Any]) -> Any:
        async with self._sessionmaker() as session:
            data["session"] = session
            return await handler(event, data)


class RedisMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._redis = get_redis_client()

    async def __call__(self, handler: Handler, event: Any, data: Dict[str, Any]) -> Any:
        data["redis"] = self._redis
        return await handler(event, data)


class ModerationMiddleware(BaseMiddleware):
    """Intercept group messages and enforce moderation heuristics."""

    async def __call__(self, handler: Handler, event: Any, data: Dict[str, Any]) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return await handler(event, data)
        if event.from_user is None or event.from_user.is_bot:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        redis: Redis | None = data.get("redis")
        bot = data.get("bot")

        if session is None or bot is None:
            return await handler(event, data)

        service = ModerationService(session, redis)
        profile = await service.get_profile()
        if profile is None:
            return await handler(event, data)

        user_id = event.from_user.id
        if user_id == settings.owner_id:
            return await handler(event, data)

        if await service.is_trusted(profile, user_id):
            return await handler(event, data)

        probation_active = await service.is_user_in_probation(
            profile=profile,
            chat_id=event.chat.id,
            user_id=user_id,
        )

        domains = extract_links(event)
        mentions = count_mentions(event)
        has_media = contains_media(event)
        text_blob = " ".join(filter(None, [event.text, event.caption]))

        violation_reason: str | None = None

        if domains:
            unauthorized = [
                domain for domain in domains if not domain_in_allowlist(domain, profile.allowed_domains)
            ]
            if unauthorized:
                violation_reason = f"Links from unapproved domains: {', '.join(unauthorized)}"
                metrics_increment("link_spam_hits")
            elif probation_active:
                violation_reason = "Links are restricted for new members during probation."
                metrics_increment("probation_link_block")

        if violation_reason is None and has_media and probation_active:
            violation_reason = "Media attachments are blocked during probation."
            metrics_increment("probation_media_block")

        if (
            violation_reason is None
            and profile.max_mentions
            and mentions > profile.max_mentions
        ):
            violation_reason = f"Message contains too many mentions ({mentions}/{profile.max_mentions})."

        additional_score = sum(
            1 for keyword in profile.ad_keywords if keyword.lower() in text_blob.lower()
        )
        ad_score = ad_keyword_score(text_blob) + additional_score
        if violation_reason is None and ad_score > 0:
            violation_reason = "Detected promotional or spam keywords."
            metrics_increment("ad_keyword_hits", ad_score)

        if violation_reason is None:
            return await handler(event, data)

        decision = await service.increment_strike(
            profile=profile,
            user_id=user_id,
            chat_id=event.chat.id,
            reason=violation_reason,
            username=event.from_user.username,
        )

        try:
            await event.delete()
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("Failed to delete message %s: %s", event.message_id, exc)
        else:
            metrics_increment("deleted_msgs")

        if decision.action in {
            ModerationAction.WARN,
            ModerationAction.MUTE,
            ModerationAction.BAN,
        }:
            warn_text = md.join_lines(
                [
                    md.bold("Moderation notice"),
                    md.escape_md(violation_reason),
                    f"Strikes: {md.inline_code(str(decision.strikes))}",
                ]
            )
            try:
                await event.answer(
                    warn_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.debug("Unable to send warning in chat %s", event.chat.id)

        if decision.action in {ModerationAction.MUTE, ModerationAction.BAN}:
            try:
                if decision.action == ModerationAction.MUTE:
                    until = decision.acted_at + timedelta(seconds=profile.mute_seconds)
                    permissions = ChatPermissions(
                        can_send_messages=False,
                        can_send_audios=False,
                        can_send_documents=False,
                        can_send_photos=False,
                        can_send_videos=False,
                        can_send_video_notes=False,
                        can_send_voice_notes=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                    )
                    await bot.restrict_chat_member(
                        chat_id=event.chat.id,
                        user_id=user_id,
                        permissions=permissions,
                        until_date=until,
                    )
                else:
                    await bot.ban_chat_member(
                        chat_id=event.chat.id,
                        user_id=user_id,
                    )
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                logger.warning("Failed applying %s to %s: %s", decision.action, user_id, exc)
        if decision.action == ModerationAction.WARN:
            metrics_increment("warns")
        elif decision.action == ModerationAction.MUTE:
            metrics_increment("mutes")
        elif decision.action == ModerationAction.BAN:
            metrics_increment("bans")

        await self._log_action(bot, profile, event, decision)
        return None

    async def _log_action(self, bot, profile, message: Message, decision) -> None:
        channel_id = profile.admin_channel_id
        if channel_id is None:
            return

        user = message.from_user
        username = md.escape_md(
            f"@{user.username}" if user and user.username else str(user.id)
        )

        log_text = md.join_lines(
            [
                md.bold("Moderation action"),
                f"Chat: {md.inline_code(str(message.chat.id))}",
                f"User: {username}",
                f"Action: {md.escape_md(decision.action)}",
                f"Reason: {md.escape_md(decision.reason)}",
                f"Strikes: {md.inline_code(str(decision.strikes))}",
            ]
        )

        try:
            await bot.send_message(
                chat_id=channel_id,
                text=log_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.debug("Failed to post moderation log: %s", exc)
