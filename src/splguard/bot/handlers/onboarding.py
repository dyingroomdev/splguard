from __future__ import annotations

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


def _welcome_keyboard(website_url: str | None, presale_url: str | None) -> InlineKeyboardMarkup:
    # Row 1: Contract and Presale
    first_row = [
        InlineKeyboardButton(text="🧾 Contract", callback_data="welcome:contract"),
        InlineKeyboardButton(
            text="💰 Presale",
            url=presale_url,
        )
        if presale_url
        else InlineKeyboardButton(text="💰 Presale", callback_data="welcome:presale"),
    ]

    # Row 2: Website and Official Links
    second_row = [
        InlineKeyboardButton(text="🌐 Website", url="https://splshield.com/"),
        InlineKeyboardButton(text="📢 Official Links", callback_data="welcome:links"),
    ]

    # Row 3: Support and Risk Scanner Bot
    third_row = [
        InlineKeyboardButton(text="🆘 Support", url="https://t.me/splsupportbot"),
        InlineKeyboardButton(text="🤖 Risk Scanner Bot", url="https://t.me/splshieldbot"),
    ]

    # Row 4: Dapp and Twitter
    fourth_row = [
        InlineKeyboardButton(text="🔷 Dapp", url="https://ex.splshield.com"),
        InlineKeyboardButton(text="🐦 Twitter", url="https://twitter.com/splshield"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=[first_row, second_row, third_row, fourth_row])


def _welcome_text(username: str | None) -> str:
    greeting_name = username or "friend"
    return md.join_lines(
        [
            f"👋 Welcome to {md.bold('SPL Shield')}, {md.escape_md(greeting_name)}{md.escape_md('!')}",
            "",
            md.escape_md("We are building the first AI powered Solana risk scanner 🛡️"),
            "",
            md.bold("Quick actions"),
            md.escape_md("💰 Presale · join while spots remain"),
            md.escape_md("🧾 Contract · verify before you trade"),
            md.escape_md("🌐 Links · stay on official channels"),
            "",
            f"{md.escape_md('⚠️ Please avoid unsolicited links or ads')} {md.escape_md('—')} {md.escape_md('spam gets removed instantly.')}",
            "",
            f"{md.escape_md('💡 For help, use')} {md.inline_code('/commands')} {md.escape_md('to see all available bot commands.')}",
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
        await callback.message.answer(
            md.escape_md("Contract details are not configured yet."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    text = render_contract_block(
        addresses=payload["contract_addresses"],
        chain="Solana",
        token_ticker=payload.get("token_ticker"),
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
        f"{md.escape_md('📅 Start:')} {md.escape_md('6 PM UTC (00+), 26th Oct 2025')}",
        f"{md.escape_md('💵 Price:')} {md.escape_md('$0.002 per TDL')}",
        f"{md.escape_md('📊 Supply:')} {md.escape_md('1B TDL')}",
        "",
        md.escape_md("Join early to secure your position before the whitelist ends!"),
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
        "Dapp": "https://ex.splshield.com",
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
