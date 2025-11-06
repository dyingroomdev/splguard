from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from aiogram import Bot
from aiogram.types import ChatInviteLink
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..metrics import increment as metrics_increment
from ..models import InviteLink, InviteStat

logger = logging.getLogger(__name__)


async def list_links(session: AsyncSession, owner_id: int) -> Sequence[InviteLink]:
    stmt: Select[InviteLink] = (
        select(InviteLink)
        .where(
            InviteLink.owner_tg_id == owner_id,
            InviteLink.chat_id == settings.splshield_chat_id,
        )
        .order_by(InviteLink.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def _create_link(
    session: AsyncSession,
    bot: Bot,
    owner_id: int,
    name: str | None = None,
) -> InviteLink:
    if settings.splshield_chat_id is None:
        raise RuntimeError("SPLSHIELD_CHAT_ID is not configured.")

    expire_date = None
    if settings.affiliates_rotate_expiry_days > 0:
        expire_date = datetime.now(timezone.utc) + timedelta(days=settings.affiliates_rotate_expiry_days)

    try:
        chat_link: ChatInviteLink = await bot.create_chat_invite_link(
            chat_id=settings.splshield_chat_id,
            creates_join_request=True,
            name=name or f"ref-{owner_id}",
            expire_date=expire_date,
            member_limit=None,
        )
    except Exception:  # pragma: no cover - network/Telegram failures
        logger.exception("Failed to create invite link for owner %s", owner_id)
        raise

    link = InviteLink(
        owner_tg_id=owner_id,
        chat_id=settings.splshield_chat_id,
        invite_link=chat_link.invite_link,
        name=chat_link.name,
        creates_join_request=chat_link.creates_join_request or False,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    metrics_increment("affiliates.links.created")
    return link


async def ensure_link(
    session: AsyncSession,
    bot: Bot,
    owner_id: int,
    name: str | None = None,
) -> InviteLink:
    existing = await active_link_for_owner(session, owner_id)
    if existing:
        return existing

    links = await list_links(session, owner_id)
    if settings.affiliates_max_links_per_user > 0 and len(links) >= settings.affiliates_max_links_per_user:
        # Trim oldest records
        for link in links[settings.affiliates_max_links_per_user - 1 :]:
            await session.delete(link)
        await session.commit()

    return await _create_link(session, bot, owner_id, name=name)


async def rotate_link(
    session: AsyncSession,
    bot: Bot,
    owner_id: int,
    name: str | None = None,
) -> InviteLink:
    if settings.splshield_chat_id is None:
        raise RuntimeError("SPLSHIELD_CHAT_ID is not configured.")
    existing = await active_link_for_owner(session, owner_id)
    if existing:
        try:
            await bot.revoke_chat_invite_link(settings.splshield_chat_id, existing.invite_link)
        except Exception:  # pragma: no cover
            logger.debug("Unable to revoke invite link %s", existing.invite_link)
        await session.delete(existing)
        await session.commit()
    return await _create_link(session, bot, owner_id, name=name)


async def record_join(session: AsyncSession, invite_link: str, joined_user_id: int) -> bool:
    entry = InviteStat(invite_link=invite_link, joined_user_id=joined_user_id)
    session.add(entry)
    try:
        await session.commit()
        metrics_increment("affiliates.joins")
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def invite_count(session: AsyncSession, invite_link: str) -> int:
    stmt = select(func.count(func.distinct(InviteStat.joined_user_id))).where(
        InviteStat.invite_link == invite_link
    )
    result = await session.execute(stmt)
    value = result.scalar()
    return int(value or 0)


async def top_inviters(session: AsyncSession, days: int | None = 7, limit: int = 10) -> list[dict[str, int]]:
    if settings.splshield_chat_id is None:
        return []

    join_conditions = [InviteLink.chat_id == settings.splshield_chat_id]
    join_clause = InviteStat.invite_link == InviteLink.invite_link

    if days and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        join_clause = and_(join_clause, InviteStat.joined_at >= cutoff)

    stmt = (
        select(
            InviteLink.owner_tg_id,
            func.count(func.distinct(InviteStat.joined_user_id)).label("joins"),
        )
        .select_from(InviteLink)
        .join(InviteStat, join_clause, isouter=True)
        .where(*join_conditions)
        .group_by(InviteLink.owner_tg_id)
        .order_by(func.count(func.distinct(InviteStat.joined_user_id)).desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = []
    for owner_id, count in result.all():
        rows.append({"owner_id": int(owner_id), "joins": int(count or 0)})
    return rows


async def get_link_by_url(session: AsyncSession, invite_url: str) -> InviteLink | None:
    stmt = select(InviteLink).where(InviteLink.invite_link == invite_url)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def active_link_for_owner(session: AsyncSession, owner_id: int) -> InviteLink | None:
    links = await list_links(session, owner_id)
    return links[0] if links else None
