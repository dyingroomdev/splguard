from __future__ import annotations

from aiogram import Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...i18n import gettext
# pylint: disable=duplicate-code
from ...metrics import get_counters, increment as metrics_increment, uptime_seconds
from ...services.content import ContentService
from ...services.presale import PresaleService
from ...templates import (
    render_contract_block,
    render_links_block,
    render_presale_block,
    render_team_cards,
)
from ...version import get_version
from ...utils import markdown as md
from ...utils.rate_limit import is_rate_limited


router = Router(name="info-handler")

RATE_LIMIT_SECONDS = 5


def _content_service(session: AsyncSession, redis: Redis | None) -> ContentService:
    return ContentService(session=session, redis=redis)


async def _rate_limited(message: Message, redis: Redis | None, command: str) -> bool:
    user_id = message.from_user.id if message.from_user else message.chat.id
    limited = await is_rate_limited(
        redis, command, f"{message.chat.id}:{user_id}", RATE_LIMIT_SECONDS
    )
    if limited:
        await message.answer("Please wait a moment before using this command again.")
    return limited


def _build_links_keyboard(links: dict[str, str]) -> InlineKeyboardMarkup | None:
    buttons = []
    for label, url in links.items():
        if url:
            friendly = label.replace("_", " ").title()
            buttons.append([InlineKeyboardButton(text=friendly, url=url)])
    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("help"))
async def handle_help(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "help"):
        return
    metrics_increment("command_usage.help")

    intro = md.escape_md(gettext("help.intro"))

    # Add support bot button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Contact Support", url="https://t.me/splshieldhelpbot")]
    ])

    await message.answer(intro, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)


@router.message(Command("commands"))
async def handle_commands(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "commands"):
        return
    metrics_increment("command_usage.commands")

    text = md.join_lines([
        f"{md.bold('📋 Available Commands')}",
        "",
        f"{md.bold('👥 Public Commands')}",
        f"{md.inline_code('/help')} {md.escape_md('- Get help and information')}",
        f"{md.inline_code('/team')} {md.escape_md('- View core team members')}",
        f"{md.inline_code('/contract')} {md.escape_md('- View token contract details')}",
        f"{md.inline_code('/presale')} {md.escape_md('- View presale information')}",
        f"{md.inline_code('/links')} {md.escape_md('- View all official links')}",
        f"{md.inline_code('/status')} {md.escape_md('- View bot status and metrics')}",
        f"{md.inline_code('/ping')} {md.escape_md('- Check if bot is online')}",
        "",
        f"{md.escape_md('💡 Tip: Click any command to use it!')}",
    ])

    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2)


@router.message(Command("team"))
async def handle_team(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "team"):
        return
    metrics_increment("command_usage.team")

    service = _content_service(session, redis)
    payload = await service.get_settings_payload()
    if not payload or not payload["team"]:
        await message.answer(md.escape_md(gettext("team.no_data")), parse_mode=ParseMode.MARKDOWN_V2)
        return

    text = render_team_cards(payload["team"])

    primary_links = {
        "Website": payload.get("website"),
        "Docs": payload.get("docs"),
    }
    keyboard = _build_links_keyboard({k: v for k, v in primary_links.items() if v})

    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)


@router.message(Command("contract"))
async def handle_contract(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "contract"):
        return
    metrics_increment("command_usage.contract")

    service = _content_service(session, redis)
    payload = await service.get_settings_payload()
    if not payload or not payload["contract_addresses"]:
        await message.answer(md.escape_md(gettext("contract.no_data")), parse_mode=ParseMode.MARKDOWN_V2)
        return

    addresses = payload["contract_addresses"]
    text = render_contract_block(
        addresses=addresses,
        chain="Solana",
        token_ticker=payload.get("token_ticker"),
        supply=payload.get("supply_display"),
        explorer_url=payload.get("explorer_url"),
    )

    keyboard = None
    if payload.get("explorer_url"):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Open Explorer", url=payload["explorer_url"])],
                [InlineKeyboardButton(text="Copy Address", switch_inline_query=addresses[0])],
            ]
        )

    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)


@router.message(Command("presale"))
async def handle_presale(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "presale"):
        return
    metrics_increment("command_usage.presale")

    presale_service = PresaleService(session, redis)
    summary = await presale_service.get_summary(refresh_external=False)
    if summary is None:
        await message.answer(md.escape_md(gettext("presale.no_data")), parse_mode=ParseMode.MARKDOWN_V2)
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
    primary_link = summary.primary_link

    keyboard = None
    if primary_link:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="View Presale", url=primary_link)]]
        )

    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)

    await presale_service.cache_summary(summary)

    if message.chat and message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await presale_service.add_watcher(message.chat.id)


@router.message(Command("links"))
async def handle_links(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "links"):
        return
    metrics_increment("command_usage.links")

    service = _content_service(session, redis)
    payload = await service.get_settings_payload()
    if not payload:
        await message.answer(md.escape_md(gettext("links.no_data")), parse_mode=ParseMode.MARKDOWN_V2)
        return

    links = {
        "Website": payload.get("website"),
        "Docs": payload.get("docs"),
        **(payload.get("social_links") or {}),
    }
    filtered_links = {k: v for k, v in links.items() if v}

    if not filtered_links:
        await message.answer(md.escape_md(gettext("links.no_data")), parse_mode=ParseMode.MARKDOWN_V2)
        return

    text = render_links_block(filtered_links)

    keyboard = _build_links_keyboard(filtered_links)

    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)


@router.message(Command("status"))
async def handle_status(message: Message, session: AsyncSession, redis: Redis | None) -> None:
    if await _rate_limited(message, redis, "status"):
        return
    metrics_increment("command_usage.status")

    db_ok = True
    redis_ok = True

    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - best effort diagnostics
        db_ok = False

    if redis is not None:
        try:
            await redis.ping()
        except Exception:
            redis_ok = False
    else:
        redis_ok = False

    counters = get_counters()
    uptime = uptime_seconds()

    text_lines = [
        md.bold("Bot Status"),
        f"Version: {md.inline_code(get_version())}",
        f"Uptime: {md.inline_code(f'{uptime:.0f}s')}",
        f"Database: {'✅' if db_ok else '❌'}",
        f"Redis: {'✅' if redis_ok else '❌'}",
        "",
        md.bold("Counters"),
    ]

    if counters:
        for key, value in sorted(counters.items()):
            text_lines.append(f"{md.escape_md(key)}: {md.inline_code(str(value))}")
    else:
        text_lines.append("(no events recorded yet)")

    await message.answer(md.join_lines(text_lines), parse_mode=ParseMode.MARKDOWN_V2)
