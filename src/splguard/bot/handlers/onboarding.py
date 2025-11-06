from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...metrics import increment as metrics_increment
from ...services import zealy as zealy_service
from ...services.content import ContentService
from ...services.moderation import ModerationService
from ...services.presale import PresaleService
from ...templates import render_contract_block, render_links_block, render_presale_block
from ...utils import markdown as md

logger = logging.getLogger(__name__)
router = Router(name="onboarding")


def _coerce_status(value: ChatMemberStatus | str | None) -> ChatMemberStatus | None:
    if isinstance(value, ChatMemberStatus):
        return value
    if value is None:
        return None
    try:
        return ChatMemberStatus(value)
    except ValueError:
        return None


def _coerce_chat_type(value: ChatType | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, ChatType):
        return value.value
    return str(value)


def _welcome_keyboard(payload: dict[str, Any] | None, presale_url: str | None) -> InlineKeyboardMarkup:
    data = payload or {}
    website_url = data.get("website")
    docs_url = data.get("docs")
    social_links = data.get("social_links") or {}
    twitter_url = social_links.get("Twitter") or "https://twitter.com/splshield"
    risk_bot_url = social_links.get("Risk Scanner App") or "https://t.me/splshieldbot"

    buttons: list[list[InlineKeyboardButton]] = []

    row_one = [
        InlineKeyboardButton(text="📜 Contract", callback_data="welcome:contract"),
        InlineKeyboardButton(
            text="💰 Presale",
            url=presale_url,
        )
        if presale_url
        else InlineKeyboardButton(text="💰 Presale", callback_data="welcome:presale"),
    ]
    buttons.append(row_one)

    row_two: list[InlineKeyboardButton] = []
    if website_url:
        row_two.append(InlineKeyboardButton(text="🌐 Website", url=website_url))
    row_two.append(InlineKeyboardButton(text="📎 Official Links", callback_data="welcome:links"))
    buttons.append(row_two)

    buttons.append([
        InlineKeyboardButton(text="🆘 Support", url="https://t.me/splsupportbot"),
        InlineKeyboardButton(text="🤖 Risk Scanner Bot", url=risk_bot_url or "https://t.me/splshieldbot"),
    ])

    buttons.append([
        InlineKeyboardButton(text="📊 Presale Info", callback_data="presale_info"),
        InlineKeyboardButton(text="👥 Shiller Board", callback_data="presale_leaderboard"),
    ])
    buttons.append([
        InlineKeyboardButton(text="🐦 Twitter", url=twitter_url or "https://twitter.com/splshield"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _welcome_text(username: str | None, title: str | None) -> str:
    greeting_name = html.escape(username) if username else "friend"
    contract = html.escape("tdLS6cTi91yLm5BD5H2Ky5Wbs5YeTTHBqfGKjQX2hoz")
    lines = [f"👋 Welcome to <b>SPL Shield</b>, <b>{greeting_name}</b>!"]
    if title:
        lines.append(f"🏷️ <b>{html.escape(title)}</b>")
    lines.extend(
        [
            "",
            "⚡️ <b>What we do</b>",
            "• AI-powered Solana risk scanning",
            "• Real-time presale monitoring",
            "",
            "💎 <b>Token essentials</b>",
            "• Total supply: <code>10B TDL</code>",
            f"• Mint: <code>{contract}</code>",
            "• Presale: 6 Nov 2025 · Ends 5 Jan 2026",
            "",
            "🚀 <b>Quick commands</b>",
            "• Use <code>/commands</code> to explore the bot",
            "• Only trust links shared by SPL Shield admins",
            "",
            "🏅 <b>Zealy quests</b>",
            "• <code>/link &lt;wallet&gt;</code> bind your wallet",
            "• <code>/quests</code> browse available quests",
            "• <code>/xp</code> check your progress",
            "• <code>/tier</code> view perks and status",
            "• <code>/submit &lt;txSig&gt;</code> verify presale buys",
        ]
    )
    return "\n".join(lines)


@router.chat_member()
async def handle_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    chat_type = _coerce_chat_type(event.chat.type)
    if chat_type not in {"group", "supergroup"}:
        return
    old_status = _coerce_status(event.old_chat_member.status)
    new_status = _coerce_status(event.new_chat_member.status)
    logger.debug(
        "chat_member update",
        extra={
            "chat_type": chat_type,
            "chat_id": event.chat.id,
            "user_id": event.new_chat_member.user.id if event.new_chat_member.user else None,
            "old_status": getattr(old_status, "value", old_status),
            "new_status": getattr(new_status, "value", new_status),
        },
    )
    if new_status != ChatMemberStatus.MEMBER or old_status == ChatMemberStatus.MEMBER:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return

    content_service = ContentService(session=session, redis=redis)
    try:
        payload = await content_service.get_settings_payload()
    except Exception:
        logger.exception("Failed to load content settings payload")
        payload = None

    presale_service = PresaleService(session, redis)
    try:
        summary = await presale_service.get_summary(refresh_external=False)
    except Exception:
        logger.exception("Failed to load presale summary")
        summary = None

    presale_url = summary.primary_link if summary else None

    try:
        member_summary = await zealy_service.get_member_summary(session, user.id)
    except Exception:
        logger.exception("Failed to load member summary for %s", user.id)
        member_summary = None
    member_title = None
    if member_summary and member_summary.get("title"):
        member_title = member_summary["title"]

    text = _welcome_text(user.full_name, member_title)
    message = await bot.send_message(
        chat_id=event.chat.id,
        text=text,
        reply_markup=_welcome_keyboard(payload, presale_url),
        parse_mode=ParseMode.HTML,
    )
    # Welcome message stays permanently (no auto-delete)
    metrics_increment("new_members.welcomed")

    moderation = ModerationService(session, redis)
    profile = await moderation.get_profile()
    if profile:
        probation_seconds = profile.probation_seconds or 600
        await moderation.set_probation(
            profile=profile,
            chat_id=event.chat.id,
            user_id=user.id,
            username=user.username,
            probation_seconds=probation_seconds,
        )
        metrics_increment("probation.assigned")

    try:
        await presale_service.add_watcher(event.chat.id)
    except Exception:
        logger.exception("Failed to register watcher for chat %s", event.chat.id)


@router.message()
async def handle_new_member_message(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if not message.new_chat_members:
        return
    chat_type = _coerce_chat_type(message.chat.type)
    if chat_type not in {"group", "supergroup"}:
        return
    logger.debug(
        "new_chat_members message",
        extra={
            "chat_type": chat_type,
            "chat_id": message.chat.id,
            "user_ids": [member.id for member in message.new_chat_members],
        },
    )
    content_service = ContentService(session=session, redis=redis)
    try:
        payload = await content_service.get_settings_payload()
    except Exception:
        logger.exception("Failed to load content settings payload (message path)")
        payload = None

    presale_service = PresaleService(session, redis)
    try:
        summary = await presale_service.get_summary(refresh_external=False)
    except Exception:
        logger.exception("Failed to load presale summary (message path)")
        summary = None
    presale_url = summary.primary_link if summary else None

    moderation = ModerationService(session, redis)
    try:
        profile = await moderation.get_profile()
    except Exception:
        logger.exception("Failed to load moderation profile")
        profile = None

    for user in message.new_chat_members:
        if user.is_bot:
            continue
        try:
            member_summary = await zealy_service.get_member_summary(session, user.id)
        except Exception:
            logger.exception("Failed to load member summary for %s (message path)", user.id)
            member_summary = None
        member_title = None
        if member_summary and member_summary.get("title"):
            member_title = member_summary["title"]
        text = _welcome_text(user.full_name, member_title)
        await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=_welcome_keyboard(payload, presale_url),
            parse_mode=ParseMode.HTML,
        )
        metrics_increment("new_members.welcomed")
        if profile:
            probation_seconds = profile.probation_seconds or 600
            await moderation.set_probation(
                profile=profile,
                chat_id=message.chat.id,
                user_id=user.id,
                username=user.username,
                probation_seconds=probation_seconds,
            )
            metrics_increment("probation.assigned")
        try:
            await presale_service.add_watcher(message.chat.id)
        except Exception:
            logger.exception("Failed to register watcher for chat %s (message path)", message.chat.id)


@router.callback_query(lambda c: c.data and c.data.startswith("welcome:"))
async def handle_welcome_buttons(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    action = callback.data.split(":", 1)[1]
    if action == "contract":
        metrics_increment("welcome.button.contract")
        await _send_contract_block(callback, session, redis)
    elif action == "presale":
        metrics_increment("welcome.button.presale")
        await _send_presale_block(callback, session, redis)
    elif action == "links":
        metrics_increment("welcome.button.links")
        await _send_links_block(callback, session, redis)
    else:
        await callback.answer("Not supported", show_alert=False)
        return
    await callback.answer()


async def _send_contract_block(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    content_service = ContentService(session=session, redis=redis)
    payload = await content_service.get_settings_payload()
    if not payload or not payload.get("contract_addresses"):
        await callback.message.answer(
            md.escape_md("Contract details are not configured yet."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    text = render_contract_block(
        addresses=payload["contract_addresses"],
        chain="Solana",
        token_ticker=payload.get("token_ticker"),
        supply=payload.get("supply_display"),
        explorer_url=payload.get("explorer_url"),
    )
    if not text.strip():
        await callback.message.answer(
            md.escape_md("Contract details are not available."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


async def _send_presale_block(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    # Try to get presale info from database
    presale_service = PresaleService(session, redis)
    summary = await presale_service.get_summary(refresh_external=False)

    # If database has presale info, use it
    if summary is not None:
        text = render_presale_block(
            status=summary.status,
            project_name=summary.project_name,
            platform=summary.platform,
            link=summary.primary_link,
            hardcap=summary.hardcap,
            softcap=summary.softcap,
            raised=summary.raised_so_far,
            start_time=summary.start_time,
            end_time=summary.end_time,
        )
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
        return

    # Otherwise, show default presale information
    text = md.join_lines([
        f"{md.bold('$TDL Presale')}",
        "",
        f"{md.bold('💰 Presale Details')}",
        f"{md.escape_md('🟢 Status:')} {md.escape_md('Running')}",
        f"{md.escape_md('⚙️ Platform:')} {md.escape_md('Smithii')}",
        f"{md.escape_md('🎯 Soft Cap:')} {md.escape_md('2100 SOL')}",
        f"{md.escape_md('🚀 Hard Cap:')} {md.escape_md('3500 SOL')}",
        f"{md.escape_md('📅 Start:')} {md.escape_md('6 November 2025 · 18:00 UTC')}",
        f"{md.escape_md('⏳ Ends:')} {md.escape_md('5 January 2026 · 18:00 UTC')}",
    ])
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


async def _send_links_block(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    # Default official links
    links = {
        "Website": "https://splshield.com/",
        "Risk Scanner App": "https://app.splshield.com/",
        "Documentation": "https://docs.splshield.com/",
        "Twitter": "https://twitter.com/splshield",
    }

    # Try to get additional links from database
    content_service = ContentService(session=session, redis=redis)
    payload = await content_service.get_settings_payload()
    if payload:
        # Override with database values if present
        if payload.get("website"):
            links["Website"] = payload["website"]
        if payload.get("docs"):
            links["Documentation"] = payload["docs"]
        # Add any additional social links
        social_links = payload.get("social_links") or {}
        for key, value in social_links.items():
            if value and key not in links:
                links[key] = value

    text = render_links_block(links)
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
