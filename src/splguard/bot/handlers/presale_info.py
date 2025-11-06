from __future__ import annotations

import html

from aiogram import Router, types
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...services import zealy as zealy_service

router = Router(name="presale-info")


@router.callback_query(lambda c: c.data == "presale_info")
async def handle_presale_info(
    callback: types.CallbackQuery,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    title_line = ""
    if callback.from_user:
        summary = await zealy_service.get_member_summary(session, callback.from_user.id)
        if summary and summary.get("title"):
            title_line = f"🏷️ <b>Title:</b> {html.escape(summary['title'])}\n"

    text = (
        "<b>📊 TDL Presale Information</b>\n\n"
        f"{title_line}"
        "💠 <b>Ticker:</b> $TDL\n"
        f"📜 <b>Contract Address:</b> <code>{settings.tdl_mint}</code>\n"
        "💰 <b>Buy:</b> <a href='https://presale.splshield.com/'>https://presale.splshield.com/</a>\n"
        "⚙️ <b>Platform:</b> Smithii Launchpad\n"
        f"🎯 <b>Soft Cap:</b> {settings.presale_soft_cap_sol} SOL\n"
        f"🚀 <b>Hard Cap:</b> {settings.presale_hard_cap_sol} SOL\n"
        "💎 <b>Rate:</b> 0.1 SOL = 75,018.75 TDL\n\n"
        "⏳ <b>Why Tokens Don’t Show in Wallet Yet</b>\n"
        "When you buy during presale, your SOL is recorded on-chain by the Smithii program, "
        "but TDL tokens remain locked until the presale officially ends (Jan 5 2026). "
        "After that, the <b>“Claim”</b> phase opens on Smithii and you’ll be able to mint or "
        "receive your tokens directly to your wallet. "
        "Your purchase is already registered on-chain, even if it doesn’t yet appear in your wallet."
    )

    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=False)
    await callback.answer()
