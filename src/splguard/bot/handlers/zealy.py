from __future__ import annotations

import random

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...metrics import increment as metrics_increment
from ...services import zealy as zealy_service
from ...services.presale import PresaleService
from ...utils import markdown as md
from ...utils.rate_limit import is_rate_limited

router = Router(name="zealy-handlers")

RATE_LIMIT_SECONDS = 5
DEFAULT_RESPONSE = (
    "Something went wrong while processing your request. Please try again later."
)
REASON_MESSAGES = {
    "rpc_not_configured": "Presale verification is not available right now. Please try later.",
    "wallet_not_linked": "Link your wallet with /link before submitting a presale transaction.",
    "tx_not_found": "We could not find that transaction on Solana. Double-check the signature.",
    "invalid_transaction": "The transaction payload looks invalid.",
    "wallet_missing": "Your wallet was not found in the transaction accounts.",
    "buyer_not_signer": "You must sign the presale transaction with your linked wallet.",
    "no_smithii_program": "This transaction does not interact with the Smithii contract.",
    "vault_not_involved": "The presale vault is not part of this transaction.",
    "tdl_not_minted": "TDL tokens were not minted in this transaction.",
    "insufficient_sol": "The SOL payment is below the required presale minimum.",
    "insufficient_usdc": "The USDC payment is below the required presale minimum.",
    "insufficient_payment": "A qualifying SOL or USDC payment was not detected.",
    "rpc_error": "The Solana RPC endpoint failed to verify your transaction. Please try again.",
    "already_submitted": "This transaction was already submitted. Reach out to support if you need help.",
}


async def _rate_limited(message: Message, redis: Redis | None, scope: str) -> bool:
    user_id = message.from_user.id if message.from_user else message.chat.id
    limited = await is_rate_limited(redis, scope, f"{user_id}", RATE_LIMIT_SECONDS)
    if limited:
        await message.answer("Too many requests — please wait a few seconds.")
    return limited


def _require_args(message: Message) -> str | None:
    if message.text is None:
        return None
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


@router.message(Command("link"))
async def handle_link(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if await _rate_limited(message, redis, "link"):
        return
    metrics_increment("command_usage.link")

    wallet = _require_args(message)
    if not wallet:
        await message.answer(
            "Usage: /link <your_solana_wallet>\n\nExample:\n/link 3Cs1QjP5c1v4xg4M8Jt6Zs37Tz7Z7ABCdEFGhijkLmno",
        )
        return

    if message.from_user is None:
        await message.answer(DEFAULT_RESPONSE)
        return

    try:
        member, status = await zealy_service.bind_wallet(
            session=session,
            telegram_id=message.from_user.id,
            wallet=wallet,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return
    except Exception:  # pragma: no cover - unexpected database errors
        await message.answer(DEFAULT_RESPONSE)
        return

    if status == "unchanged":
        reply = "Your wallet is already linked ✅"
    elif status == "created":
        reply = "Wallet linked! You're now connected to Zealy."
    else:
        reply = "Wallet updated successfully."

    if member.tier:
        reply += f"\nCurrent tier: {zealy_service.tier_label(member.tier)}"

    await message.answer(reply)


@router.message(Command("quests"))
async def handle_quests(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if await _rate_limited(message, redis, "quests"):
        return
    metrics_increment("command_usage.quests")

    quests = await zealy_service.list_active_quests(session=session)
    if not quests:
        await message.answer("No active Zealy quests yet. Check back soon!")
        return

    lines = [
        md.bold("Active Zealy Quests"),
        "",
    ]
    for quest in quests:
        xp = f"{quest.xp_value} XP"
        lines.append(f"{md.inline_code(quest.slug)} — {md.escape_md(xp)}")
    text = md.join_lines(lines)
    await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2)


@router.message(Command("xp"))
async def handle_xp(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if await _rate_limited(message, redis, "xp"):
        return
    metrics_increment("command_usage.xp")

    if message.from_user is None:
        await message.answer(DEFAULT_RESPONSE)
        return

    summary = await zealy_service.get_member_summary(
        session=session,
        telegram_id=message.from_user.id,
    )
    if summary is None:
        await message.answer("Link your wallet first with /link to start earning XP.")
        return

    tier_label = summary["tier_label"]

    lines = [
        md.bold("Zealy Progress"),
        f"XP: {md.inline_code(str(summary['xp']))}",
        f"Level: {md.inline_code(str(summary['level']))}",
        f"Tier: {md.escape_md(tier_label)}",
    ]
    if summary["wallet"]:
        lines.append(f"Wallet: {md.inline_code(summary['wallet'])}")

    rewards = summary["recent_rewards"]
    if rewards:
        lines.append("")
        lines.append(md.bold("Recent Rewards"))
        for reward in rewards:
            quest_label = reward["quest"] or "Quest"
            xp_text = f"{reward['xp']} XP" if reward["xp"] else "XP pending"
            status = reward["status"]
            lines.append(
                f"{md.inline_code(quest_label)} — {md.escape_md(xp_text)} ({md.escape_md(status)})"
            )

    await message.answer(md.join_lines(lines), parse_mode=ParseMode.MARKDOWN_V2)


@router.message(Command("tier"))
async def handle_tier(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if await _rate_limited(message, redis, "tier"):
        return
    metrics_increment("command_usage.tier")

    if message.from_user is None:
        await message.answer(DEFAULT_RESPONSE)
        return

    summary = await zealy_service.get_member_summary(
        session=session,
        telegram_id=message.from_user.id,
    )
    if summary is None:
        await message.answer("Link your wallet with /link to unlock your tier.")
        return

    tier_label = summary["tier_label"]
    privileges = summary["privileges"]

    lines = [md.bold("Current Tier"), md.escape_md(tier_label)]
    if privileges:
        lines.extend([
            "",
            md.bold("Privileges"),
            *[md.escape_md(f"• {item}") for item in privileges],
        ])

    await message.answer(md.join_lines(lines), parse_mode=ParseMode.MARKDOWN_V2)


@router.message(Command("submit"))
async def handle_submit(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> None:
    if await _rate_limited(message, redis, "submit"):
        return
    metrics_increment("command_usage.submit")

    tx_sig = _require_args(message)
    if not tx_sig:
        await message.answer(
            "Usage: /submit <transaction_signature>\n\nExample:\n/submit 3D1CgVw1oC4QqG3b5LVj8G2Xkhp3S5x8zK8S7R2nkfC9xJ9YEr1fTnQ3UEJ9T1o3kcee8gX2cz2r",
        )
        return

    if message.from_user is None:
        await message.answer(DEFAULT_RESPONSE)
        return

    summary = await zealy_service.get_member_summary(
        session=session,
        telegram_id=message.from_user.id,
    )
    if summary is None or not summary.get("wallet"):
        await message.answer("Link your wallet with /link before submitting a transaction.")
        return

    if redis is not None:
        cooldown_key = f"submit:cooldown:{message.from_user.id}"
        stored = await redis.set(cooldown_key, "1", ex=60, nx=True)
        if stored is None:
            await message.answer("Please wait a minute before submitting another transaction.")
            return

    member = summary["member"]
    presale_service = PresaleService(session, redis)
    verification = await presale_service.verify_submission(tx_sig, member)
    if not verification.get("ok"):
        reason = verification.get("reason") or "verification_failed"
        friendly = REASON_MESSAGES.get(reason, f"Verification failed: {reason}")
        await message.answer(friendly)
        return

    amount = verification.get("amount")
    currency = verification.get("currency")
    payment_line = None
    if amount is not None and currency:
        if currency.upper() == "SOL":
            payment_line = f"Payment: {md.inline_code(f'{amount:.6f} SOL')}"
        else:
            payment_line = f"Payment: {md.inline_code(f'{amount:.2f} {currency}')}"

    lines = [
        md.bold("Presale Verified ✅"),
        f"Transaction: {md.inline_code(tx_sig)}",
    ]
    if payment_line:
        lines.append(payment_line)
    if settings.zealy_presale_xp_reward:
        lines.append(f"Reward: {md.inline_code(f'+{settings.zealy_presale_xp_reward} XP')}")
    lines.append("Zealy quest recorded — check /xp for your rewards!")

    spot_check = False
    if redis is not None and random.random() < 0.1:
        spot_check = True
        await zealy_service.enqueue_dlq(
            redis,
            {
                "tx_signature": tx_sig,
                "telegram_id": member.telegram_id,
                "wallet": member.wallet,
                "reason": "spot_check",
            },
        )

    await message.answer(md.join_lines(lines), parse_mode=ParseMode.MARKDOWN_V2)

    if verification.get("tier_changed"):
        new_tier = verification.get("new_tier")
        tier_name = zealy_service.tier_label(new_tier)
        await message.answer(
            md.join_lines(
                [
                    "🎉",
                    md.bold(f"Tier upgraded to {tier_name}!"),
                    md.escape_md("Enjoy the new perks."),
                ]
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    if spot_check:
        await message.answer(
            md.escape_md("🛡️ Selected for a spot check — our team will double-check your transaction."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
