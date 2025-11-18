from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import PresaleStatus
from ...metrics import get_counters, increment as metrics_increment
from ...services.admin import AdminService, TeamEntry
from ...services.audit import format_diff, log_admin_action
from ...services.moderation import ModerationService
from ...services.presale import PresaleService
from ...utils import markdown as md
from ...utils.rate_limit import is_rate_limited


router = Router(name="admin-dispatcher")

RATE_LIMIT_SECONDS = 5
PENDING_TTL_SECONDS = 180
PENDING_KEY_TEMPLATE = "admin:pending:{user_id}"


@dataclass
class PendingAction:
    action: str
    payload: Dict[str, Any]
    description: str


def _pending_key(user_id: int) -> str:
    return PENDING_KEY_TEMPLATE.format(user_id=user_id)


def _describe_team(member: TeamEntry | None) -> str:
    if member is None:
        return "-"
    parts = [f"#{member.id} {member.name}"]
    if member.role:
        parts.append(f"Role={member.role}")
    if member.contact:
        parts.append(f"Contact={member.contact}")
    parts.append(f"Order={member.display_order}")
    return " | ".join(parts)


async def _check_admin(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
) -> tuple[ModerationService, Any, bool]:
    moderation = ModerationService(session, redis)
    profile = await moderation.get_profile()
    if profile is None:
        await message.answer("Presale/configuration data is not ready. Seed the database first.")
        return moderation, None, False
    user_id = message.from_user.id if message.from_user else 0
    if not await moderation.is_admin(profile, user_id):
        await message.answer("You are not authorized to use admin commands.")
        return moderation, profile, False
    return moderation, profile, True


async def _rate_limited(message: Message, redis: Redis | None) -> bool:
    user_id = message.from_user.id if message.from_user else message.chat.id
    limited = await is_rate_limited(redis, "admin", f"{user_id}", RATE_LIMIT_SECONDS)
    if limited:
        await message.answer("Admin actions are rate-limited. Please wait a moment.")
    return limited


async def _store_pending(redis: Redis, user_id: int, action: PendingAction) -> None:
    await redis.set(
        _pending_key(user_id),
        json.dumps({
            "action": action.action,
            "payload": action.payload,
            "description": action.description,
        }),
        ex=PENDING_TTL_SECONDS,
    )


async def _pop_pending(redis: Redis, user_id: int) -> Optional[PendingAction]:
    raw = await redis.get(_pending_key(user_id))
    if not raw:
        return None
    await redis.delete(_pending_key(user_id))
    data = json.loads(raw)
    return PendingAction(action=data["action"], payload=data["payload"], description=data.get("description", ""))


@router.message(Command("admin"))
async def handle_admin(
    message: Message,
    session: AsyncSession,
    redis: Redis | None,
    bot,
) -> None:
    if message.text is None or message.from_user is None:
        return

    if await _rate_limited(message, redis):
        return

    moderation, profile, authorized = await _check_admin(message, session, redis)
    if not authorized:
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Usage: /admin set contract … | team add/edit/del … | links set … | rules show/set … | export logs <days> | presale …",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    command = parts[1].lower()
    metrics_increment("command_usage.admin")

    if command == "confirm":
        if redis is None:
            await message.answer("Confirmation requires Redis to be available.")
            return
        pending = await _pop_pending(redis, message.from_user.id)
        if pending is None:
            await message.answer("No pending admin action to confirm.")
            return
        await _apply_pending_action(message, session, redis, bot, pending)
        return

    admin_service = AdminService(session)
    presale_service = PresaleService(session, redis)

    if command == "rules" and len(parts) >= 3 and parts[2].lower() == "show":
        rule = await admin_service.get_rules()
        if rule is None:
            text = "No moderation rules configured yet."
        else:
            text = md.join_lines(
                [
                    md.bold("Moderation Rules"),
                    f"Policy: {md.escape_md(rule.link_posting_policy)}",
                    f"Allowed domains: {md.escape_md(', '.join(rule.allowed_domains or []))}",
                    f"Ad keywords: {md.escape_md(', '.join(rule.ad_keywords or []))}",
                    f"Max mentions: {md.inline_code(str(rule.max_mentions))}",
                    f"Probation: {md.inline_code(str(rule.new_user_probation_duration))} sec",
                ]
            )
        await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2)
        return

    if command == "export" and len(parts) >= 4 and parts[2].lower() == "logs":
        days = int(parts[3])
        entries = await admin_service.export_logs(days)
        if not entries:
            text = "No log entries found for the requested timeframe."
        else:
            body = []
            for entry in entries[:25]:
                body.append(
                    f"User {md.inline_code(entry['user_id'])} ({md.escape_md(entry['username'] or '-')}) – strikes {md.inline_code(entry['strikes'])} – {md.escape_md(entry['updated_at'])}"
                )
            text = md.join_lines([md.bold("Recent sanctions"), *body])
        await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2)
        await log_admin_action(
            bot=bot,
            actor_id=message.from_user.id,
            action="export_logs",
            diff=format_diff("-", f"Exported {len(entries)} entries for {days} day(s)"),
        )
        return

    try:
        pending = await _build_pending_action(
            command=command,
            parts=parts,
            admin_service=admin_service,
            presale_service=presale_service,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return

    if pending is None:
        # Command executed immediately inside _build_pending_action
        return

    if redis is None:
        await message.answer("Cannot stage confirmation without Redis. Command aborted.")
        return

    await _store_pending(redis, message.from_user.id, pending)
    diff_message = md.join_lines(
        [
            md.bold("Pending admin action"),
            pending.description,
            "Reply with /admin confirm within 3 minutes to apply.",
        ]
    )
    await message.answer(diff_message, parse_mode=ParseMode.MARKDOWN_V2)


async def _apply_pending_action(message: Message, session: AsyncSession, redis: Redis | None, bot, pending: PendingAction) -> None:
    admin_service = AdminService(session)
    presale_service = PresaleService(session, redis)
    action = pending.action
    metrics_increment(f"admin_action.confirmed.{action}")

    if action == "set_contract":
        before, after = await admin_service.set_contract(pending.payload["addresses"])
        diff = format_diff(", ".join(before), ", ".join(after))
        await message.answer("Contract addresses updated.")
    elif action == "team_add":
        member = await admin_service.add_team_member(**pending.payload)
        diff = format_diff("-", _describe_team(member))
        await message.answer("Team member added.")
    elif action == "team_edit":
        before_entry, after_entry = await admin_service.edit_team_member(
            member_id=pending.payload["member_id"],
            updates=pending.payload["updates"],
        )
        diff = format_diff(_describe_team(before_entry), _describe_team(after_entry))
        await message.answer("Team member updated.")
    elif action == "team_delete":
        entry = await admin_service.delete_team_member(pending.payload["member_id"])
        diff = format_diff(_describe_team(entry), "-")
        await message.answer("Team member removed.")
    elif action == "link_set":
        before, after = await admin_service.set_link(pending.payload["key"], pending.payload["url"])
        diff = format_diff(before, after)
        await message.answer("Link updated.")
    elif action == "rule_set":
        before, after = await admin_service.set_rule_field(
            pending.payload["field"], pending.payload["value"]
        )
        diff = format_diff(before, after)
        await message.answer("Moderation rule updated.")
    elif action == "presale_status":
        previous = await presale_service.get_summary(refresh_external=False)
        summary = await presale_service.update_presale(status=PresaleStatus(pending.payload["status"]))
        old_status = previous.status if previous else "-"
        new_status = summary.status if summary else pending.payload["status"]
        diff = format_diff(old_status, new_status)
        await message.answer("Presale status updated.")
    elif action == "presale_link":
        previous = await presale_service.get_summary(refresh_external=False)
        summary = await presale_service.update_presale(links=pending.payload["links"])
        old_link = previous.primary_link if previous else "-"
        new_link = pending.payload["links"].get("primary", "")
        diff = format_diff(old_link, new_link)
        await message.answer("Presale link updated.")
    elif action == "presale_times":
        previous = await presale_service.get_summary(refresh_external=False)
        summary = await presale_service.update_presale(
            start_time=_deserialize_datetime(pending.payload.get("start")),
            end_time=_deserialize_datetime(pending.payload.get("end")),
        )
        old_range = f"{previous.start_time if previous else '-'} → {previous.end_time if previous else '-'}"
        new_range = f"{pending.payload.get('start_raw', '')} → {pending.payload.get('end_raw', '')}"
        diff = format_diff(old_range, new_range)
        await message.answer("Presale schedule updated.")
    else:
        await message.answer("Pending action is no longer supported.")
        return

    await log_admin_action(
        bot=bot,
        actor_id=message.from_user.id,
        action=action,
        diff=diff,
    )


async def _build_pending_action(
    command: str,
    parts: list[str],
    admin_service: AdminService,
    presale_service: PresaleService,
) -> Optional[PendingAction]:
    if command == "set" and len(parts) >= 3 and parts[2].lower() == "contract":
        addresses = _parse_addresses(parts[3:])
        settings = await admin_service.get_settings_snapshot()
        before = ", ".join(settings.contract_addresses or [])
        after = ", ".join(addresses)
        description = md.join_lines([
            f"Action: {md.inline_code('set_contract')}",
            format_diff(before, after),
        ])
        return PendingAction(
            action="set_contract",
            payload={"addresses": addresses},
            description=description,
        )

    if command == "team" and len(parts) >= 3:
        sub = parts[2].lower()
        if sub == "add":
            name, role, contact, order = _parse_team_fields(parts[3:])
            after = _describe_team(
                TeamEntry(id=0, name=name, role=role, contact=contact, display_order=order)
            )
            description = md.join_lines([
                f"Action: {md.inline_code('team_add')}",
                format_diff("-", after),
            ])
            return PendingAction(
                action="team_add",
                payload={
                    "name": name,
                    "role": role,
                    "contact": contact,
                    "display_order": order,
                },
                description=description,
            )
        if sub == "edit" and len(parts) >= 4:
            member_id = int(parts[3])
            updates = _parse_team_updates(parts[4:])
            before_entry, after_entry = await _preview_team_edit(admin_service, member_id, updates)
            description = md.join_lines([
                f"Action: {md.inline_code('team_edit')}",
                format_diff(_describe_team(before_entry), _describe_team(after_entry)),
            ])
            return PendingAction(
                action="team_edit",
                payload={"member_id": member_id, "updates": updates},
                description=description,
            )
        if sub == "del" and len(parts) >= 4:
            member_id = int(parts[3])
            preview = await _preview_team_delete(admin_service, member_id)
            description = md.join_lines([
                f"Action: {md.inline_code('team_delete')}",
                format_diff(_describe_team(preview), "-"),
            ])
            return PendingAction(
                action="team_delete",
                payload={"member_id": member_id},
                description=description,
            )
        raise ValueError("Usage: /admin team add Name|Role|Contact|Order | edit <id> fields | del <id>")

    if command == "links" and len(parts) >= 4 and parts[2].lower() == "set":
        key = parts[3]
        if len(parts) < 5:
            raise ValueError("Provide a URL for the link.")
        url = parts[4]
        links = await admin_service.get_links()
        before = links.get(key.lower())
        after = url
        description = md.join_lines([
            f"Action: {md.inline_code('link_set')}",
            format_diff(before, after),
        ])
        return PendingAction(
            action="link_set",
            payload={"key": key, "url": url},
            description=description,
        )

    if command == "rules" and len(parts) >= 3 and parts[2].lower() == "set" and len(parts) >= 5:
        field = parts[3]
        value = " ".join(parts[4:])
        rule = await admin_service.get_rules()
        before = "" if rule is None else getattr(rule, field, "") if hasattr(rule, field) else ""
        description = md.join_lines([
            f"Action: {md.inline_code('rule_set')}",
            format_diff(str(before), value),
        ])
        return PendingAction(
            action="rule_set",
            payload={"field": field, "value": value},
            description=description,
        )

    if command == "presale" and len(parts) >= 3:
        action = parts[2].lower()
        if action == "status" and len(parts) >= 4:
            status_value = parts[3].lower()
            if status_value not in {item.value for item in PresaleStatus}:
                raise ValueError("Status must be one of upcoming, active, ended.")
            summary = await presale_service.get_summary(refresh_external=False)
            current = summary.status if summary else "-"
            description = md.join_lines([
                f"Action: {md.inline_code('presale_status')}",
                format_diff(current, status_value),
            ])
            return PendingAction(
                action="presale_status",
                payload={"status": status_value},
                description=description,
            )
        if action == "link" and len(parts) >= 4:
            url = parts[3]
            summary = await presale_service.get_summary(refresh_external=False)
            current = summary.primary_link if summary else "-"
            description = md.join_lines([
                f"Action: {md.inline_code('presale_link')}",
                format_diff(current, url),
            ])
            return PendingAction(
                action="presale_link",
                payload={"links": {"primary": url}},
                description=description,
            )
        if action == "times" and len(parts) >= 5:
            start_raw, end_raw = parts[3], parts[4]
            start_norm = _normalize_datetime(start_raw)
            end_norm = _normalize_datetime(end_raw)
            summary = await presale_service.get_summary(refresh_external=False)
            current_range = f"{summary.start_time if summary else '-'} → {summary.end_time if summary else '-'}"
            return PendingAction(
                action="presale_times",
                payload={
                    "start": start_norm,
                    "end": end_norm,
                    "start_raw": start_raw,
                    "end_raw": end_raw,
                },
                description=md.join_lines([
                    f"Action: {md.inline_code('presale_times')}",
                    format_diff(current_range, f"{start_raw} → {end_raw}"),
                ]),
            )
        raise ValueError("Usage: /admin presale status <value> | link <url> | times <start> <end>")

    raise ValueError("Unknown admin subcommand.")


def _parse_addresses(parts: list[str]) -> list[str]:
    if not parts:
        raise ValueError("Provide at least one contract address.")
    joined = " ".join(parts)
    addresses = [item.strip() for item in joined.replace(";", ",").split(",") if item.strip()]
    if not addresses:
        raise ValueError("Provide at least one contract address.")
    return addresses


def _parse_team_fields(tokens: list[str]) -> tuple[str, str | None, str | None, int]:
    if not tokens:
        raise ValueError("Provide team data as Name|Role|Contact|Order")
    data = " ".join(tokens).split("|")
    if len(data) < 1:
        raise ValueError("Provide team data as Name|Role|Contact|Order")
    name = data[0].strip()
    role = data[1].strip() if len(data) > 1 else None
    contact = data[2].strip() if len(data) > 2 else None
    order = int(data[3].strip()) if len(data) > 3 and data[3].strip().isdigit() else 0
    if not name:
        raise ValueError("Team member name cannot be empty.")
    return name, role, contact, order


def _parse_team_updates(tokens: list[str]) -> Dict[str, Any]:
    if not tokens:
        raise ValueError("Provide updates as Name|Role|Contact|Order")
    name, role, contact, order = _parse_team_fields(tokens)
    updates: Dict[str, Any] = {}
    if name:
        updates["name"] = name
    updates["role"] = role
    updates["contact"] = contact
    updates["display_order"] = order
    return updates


async def _preview_team_edit(admin_service: AdminService, member_id: int, updates: Dict[str, Any]) -> tuple[TeamEntry, TeamEntry]:
    before = await admin_service.get_team_member(member_id)
    temp = TeamEntry(
        id=before.id,
        name=before.name,
        role=before.role,
        contact=before.contact,
        display_order=before.display_order,
    )
    if "name" in updates:
        temp.name = updates["name"]
    if "role" in updates:
        temp.role = updates["role"]
    if "contact" in updates:
        temp.contact = updates["contact"]
    if "display_order" in updates and updates["display_order"] is not None:
        temp.display_order = int(updates["display_order"])
    return before, temp


async def _preview_team_delete(admin_service: AdminService, member_id: int) -> TeamEntry:
    return await admin_service.get_team_member(member_id)


def _normalize_datetime(value: str) -> Optional[str]:
    candidate = value.strip()
    if candidate.lower() in {"none", "null", "-"}:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("Use ISO8601 timestamps, e.g. 2024-05-01T12:00:00+00:00") from exc
    return dt.isoformat()


def _deserialize_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)
