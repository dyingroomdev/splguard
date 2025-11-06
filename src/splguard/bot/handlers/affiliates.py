from __future__ import annotations

import html
from typing import Any

from aiogram import Router, types
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.types import ChatJoinRequest, ChatMemberUpdated, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...metrics import increment as metrics_increment
from ...services import affiliates as affiliate_service
from ...services.audit import log_admin_action
from ...services.moderation import ModerationService
from ...utils import markdown as md

router = Router(name="affiliates")


def _is_affiliates_enabled() -> bool:
    return settings.affiliates_enabled and settings.splshield_chat_id is not None


async def _ensure_admin(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> bool:
    moderation = ModerationService(session, redis)
    profile = await moderation.get_profile()
    if profile is None:
        await message.answer("Affiliates data is not ready yet.")
        return False
    user_id = message.from_user.id if message.from_user else 0
    if not await moderation.is_admin(profile, user_id):
        await message.answer("Admins only.")
        return False
    return True


async def _notify_shiller(bot, owner_id: int, user: types.User) -> None:
    if not settings.affiliates_notify_shiller:
        return
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=(
                f"🎉 New member joined via your link: <b>{html.escape(user.full_name)}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:  # pragma: no cover
        router.logger.debug("Unable to notify shiller %s about join", owner_id)


@router.message(Command("ref"))
async def handle_ref_command(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if not _is_affiliates_enabled():
        await message.answer("Affiliate links are not enabled.")
        return
    if message.from_user is None:
        return

    name = None
    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) > 1:
        name = parts[1][:32]

    link = await affiliate_service.ensure_link(
        session=session,
        bot=bot,
        owner_id=message.from_user.id,
        name=name,
    )
    count = await affiliate_service.invite_count(session, link.invite_link)
    await message.answer(
        "<b>Your SPL Shield invite</b>\n"
        f"{link.invite_link}\n\n"
        f"👥 Approved joins credited: <b>{count}</b>\n"
        "Share this link only; the public group link cannot track your invites.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("myinvites"))
async def handle_myinvites(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if message.from_user is None:
        return
    if not _is_affiliates_enabled():
        await message.answer("Affiliate links are not enabled.")
        return
    links = await affiliate_service.list_links(session, message.from_user.id)
    if not links:
        await message.answer("You do not have any referral links yet. Use /ref to create one.")
        return
    lines = [md.bold("Your referral links"), ""]
    for link in links:
        count = await affiliate_service.invite_count(session, link.invite_link)
        lines.append(
            f"{md.escape_md(link.invite_link)} — {md.inline_code(str(count))} joins"
        )
    await message.answer(md.join_lines(lines), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


@router.message(Command("shillers"))
async def handle_shillers(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if not await _ensure_admin(message, session, redis):
        return
    if not _is_affiliates_enabled():
        await message.answer("Affiliate links are not enabled.")
        return

    summary = await affiliate_service.top_inviters(session, days=7, limit=10)
    if not summary:
        await message.answer("No referral activity recorded yet.")
        return

    lines = ["<b>Top Shillers (7d)</b>"]
    for idx, row in enumerate(summary, start=1):
        mention = f"<a href='tg://user?id={row['owner_id']}'>{row['owner_id']}</a>"
        lines.append(f"{idx}. {mention} — <b>{row['joins']}</b> joins")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("rotateref"))
async def handle_rotateref(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if message.from_user is None:
        return
    if not _is_affiliates_enabled():
        await message.answer("Affiliate links are not enabled.")
        return

    # Re-create link by simply calling create_link (which enforces per-user max)
    link = await affiliate_service.rotate_link(
        session=session,
        bot=bot,
        owner_id=message.from_user.id,
        name=f"ref-{message.from_user.id}",
    )
    await message.answer(
        md.join_lines(
            [
                md.bold("Referral link rotated"),
                md.escape_md(link.invite_link),
            ]
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@router.message(Command("aff"))
async def handle_aff_command(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if not await _ensure_admin(message, session, redis):
        return
    enabled_text = "enabled" if settings.affiliates_enabled else "disabled"
    await message.answer(
        f"Affiliates are currently <b>{enabled_text}</b>. Toggle via environment settings.",
        parse_mode="HTML",
    )


@router.chat_join_request()
async def handle_join_request(
    event: ChatJoinRequest,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if not _is_affiliates_enabled():
        return
    invite_link = event.invite_link
    if invite_link is None:
        return

    link = await affiliate_service.get_link_by_url(session, invite_link.invite_link)
    if link is None:
        return

    try:
        await bot.approve_chat_join_request(event.chat.id, event.from_user.id)
    except Exception:  # pragma: no cover
        logger = router.logger  # use router logger
        logger.exception("Failed to approve join request for %s", event.from_user.id)
        return

    stored = await affiliate_service.record_join(session, link.invite_link, event.from_user.id)
    if stored:
        await _notify_shiller(bot, link.owner_tg_id, event.from_user)
        metrics_increment("affiliates.joins_processed")
    metrics_increment("affiliates.joins_processed")


@router.chat_member()
async def handle_chat_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if not _is_affiliates_enabled():
        return
    if event.new_chat_member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.OWNER}:
        return
    if event.invite_link is None or event.from_user is None:
        return

    link = await affiliate_service.get_link_by_url(session, event.invite_link.invite_link)
    if link is None:
        return

    stored = await affiliate_service.record_join(session, link.invite_link, event.from_user.id)
    if stored:
        await _notify_shiller(bot, link.owner_tg_id, event.from_user)
