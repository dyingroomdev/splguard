from __future__ import annotations

import logging
from typing import Iterable

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from ..config import settings
from ..metrics import increment as metrics_increment
from ..utils import markdown as md

logger = logging.getLogger(__name__)


def format_diff(before: str | None, after: str | None) -> str:
    before_text = md.escape_md(before or "-")
    after_text = md.escape_md(after or "-")
    return md.join_lines(
        [
            md.bold("Before:"),
            before_text,
            md.bold("After:"),
            after_text,
        ]
    )


async def log_admin_action(bot, actor_id: int, action: str, diff: str) -> None:
    channel_id = settings.admin_channel_id or settings.owner_id
    if channel_id is None:
        return
    lines = [
        md.bold("Admin Action"),
        f"Actor: {md.inline_code(str(actor_id))}",
        f"Action: {md.escape_md(action)}",
        diff,
    ]
    message = md.join_lines(lines)
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
        metrics_increment(f"admin_action.{action}")
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.debug("Failed to send admin audit log: %s", exc)
