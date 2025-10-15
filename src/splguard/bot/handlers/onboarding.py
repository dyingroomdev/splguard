from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...metrics import increment as metrics_increment
from ...services.content import ContentService
from ...services.moderation import ModerationService
from ...services.presale import PresaleService
from ...templates import render_contract_block, render_links_block, render_presale_block
from ...utils import markdown as md

router = Router(name="onboarding")

WELCOME_DELETE_AFTER = 60


async def _schedule_delete(message: Message) -> None:
    async def _delete_later() -> None:
        await asyncio.sleep(WELCOME_DELETE_AFTER)
        with suppress(Exception):
            await message.delete()

    asyncio.create_task(_delete_later())


def _welcome_keyboard(website_url: str | None, presale_url: str | None) -> InlineKeyboardMarkup:
    first_row = [
        InlineKeyboardButton(text="🧾 Contract", callback_data="welcome:contract"),
        InlineKeyboardButton(
            text="💰 Presale",
            url=presale_url,
        )
        if presale_url
        else InlineKeyboardButton(text="💰 Presale", callback_data="welcome:presale"),
    ]
    second_row = [
        InlineKeyboardButton(text="🌐 Website", url=website_url)
        if website_url
        else InlineKeyboardButton(text="🌐 Website", callback_data="welcome:links"),
        InlineKeyboardButton(text="📢 Official Links", callback_data="welcome:links"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[first_row, second_row])


def _welcome_text(username: str | None) -> str:
    greeting_name = username or "friend"
    return md.join_lines(
        [
            f"👋 Welcome to {md.bold('SPL Shield')}, {md.escape_md(greeting_name)}!",
            "",
            "We are building the first AI powered Solana risk scanner 🛡️",
            "",
            md.bold("Quick actions"),
            "💰 Presale · join while spots remain",
            "🧾 Contract · verify before you trade",
            "🌐 Links · stay on official channels",
            "",
            "Please avoid unsolicited links or ads — spam gets removed instantly.",
        ]
    )


@router.chat_member()
async def handle_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if event.chat.type not in ("group", "supergroup"):
        return
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if new_status != ChatMemberStatus.MEMBER or old_status == ChatMemberStatus.MEMBER:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return

    content_service = ContentService(session=session, redis=redis)
    payload = await content_service.get_settings_payload()

    presale_service = PresaleService(session, redis)
    summary = await presale_service.get_summary(refresh_external=False)

    website_url = payload.get("website") if payload else None
    presale_url = summary.primary_link if summary else None

    text = _welcome_text(user.full_name)
    message = await bot.send_message(
        chat_id=event.chat.id,
        text=text,
        reply_markup=_welcome_keyboard(website_url, presale_url),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _schedule_delete(message)
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

    await presale_service.add_watcher(event.chat.id)


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
        await callback.message.answer("Contract details are not configured yet.")
        return
    text = render_contract_block(
        addresses=payload["contract_addresses"],
        chain="Solana",
        token_ticker=payload.get("token_ticker"),
        explorer_url=payload.get("explorer_url"),
    )
    if not text.strip():
        await callback.message.answer("Contract details are not available.")
        return
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


async def _send_presale_block(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    presale_service = PresaleService(session, redis)
    summary = await presale_service.get_summary(refresh_external=False)
    if summary is None:
        await callback.message.answer("Presale information is not available.")
        return
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


async def _send_links_block(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    content_service = ContentService(session=session, redis=redis)
    payload = await content_service.get_settings_payload()
    if not payload:
        await callback.message.answer("Official links are not configured yet.")
        return
    links = {
        "Website": payload.get("website"),
        "Docs": payload.get("docs"),
        **(payload.get("social_links") or {}),
    }
    text = render_links_block({k: v for k, v in links.items() if v})
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
