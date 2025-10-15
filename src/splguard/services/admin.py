from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import ModerationRule, Settings, TeamMember, UserInfraction


@dataclass
class TeamEntry:
    id: int
    name: str
    role: str | None
    contact: str | None
    display_order: int

    @classmethod
    def from_model(cls, member: TeamMember) -> "TeamEntry":
        return cls(
            id=member.id,
            name=member.name,
            role=member.role,
            contact=member.contact,
            display_order=member.display_order,
        )


class AdminService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_settings(self) -> Settings:
        stmt = select(Settings).options(selectinload(Settings.team_members)).limit(1)
        result = await self._session.execute(stmt)
        settings = result.scalar_one_or_none()
        if settings is None:
            raise ValueError("Settings record not found. Seed the database first.")
        return settings

    async def get_settings_snapshot(self) -> Settings:
        return await self._get_settings()

    async def list_team(self) -> list[TeamEntry]:
        settings = await self._get_settings()
        members = sorted(
            settings.team_members,
            key=lambda member: (member.display_order, member.id),
        )
        return [TeamEntry.from_model(member) for member in members]

    async def get_links(self) -> dict[str, str]:
        settings = await self._get_settings()
        return dict(settings.social_links or {})

    async def set_contract(self, addresses: Iterable[str]) -> tuple[list[str], list[str]]:
        settings = await self._get_settings()
        before = list(settings.contract_addresses or [])
        normalized = [addr.strip() for addr in addresses if addr.strip()]
        if not normalized:
            raise ValueError("Provide at least one contract address.")
        settings.contract_addresses = normalized
        await self._session.commit()
        return before, normalized

    async def add_team_member(
        self, name: str, role: str | None, contact: str | None, display_order: int
    ) -> TeamEntry:
        settings = await self._get_settings()
        member = TeamMember(
            settings_id=settings.id,
            name=name,
            role=role or "",
            contact=contact or "",
            display_order=display_order,
        )
        self._session.add(member)
        await self._session.commit()
        await self._session.refresh(member)
        return TeamEntry.from_model(member)

    async def edit_team_member(
        self,
        member_id: int,
        updates: Mapping[str, str | int | None],
    ) -> tuple[TeamEntry, TeamEntry]:
        stmt = select(TeamMember).where(TeamMember.id == member_id).limit(1)
        result = await self._session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            raise ValueError("Team member not found.")

        before = TeamEntry.from_model(member)

        if "name" in updates and updates["name"]:
            member.name = str(updates["name"])
        if "role" in updates:
            member.role = str(updates["role"] or "")
        if "contact" in updates:
            member.contact = str(updates["contact"] or "")
        if "display_order" in updates and updates["display_order"] is not None:
            member.display_order = int(updates["display_order"])

        await self._session.commit()
        await self._session.refresh(member)
        after = TeamEntry.from_model(member)
        return before, after

    async def delete_team_member(self, member_id: int) -> TeamEntry:
        stmt = select(TeamMember).where(TeamMember.id == member_id).limit(1)
        result = await self._session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            raise ValueError("Team member not found.")
        snapshot = TeamEntry.from_model(member)
        await self._session.delete(member)
        await self._session.commit()
        return snapshot

    async def get_team_member(self, member_id: int) -> TeamEntry:
        stmt = select(TeamMember).where(TeamMember.id == member_id).limit(1)
        result = await self._session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            raise ValueError("Team member not found.")
        return TeamEntry.from_model(member)

    async def set_link(self, key: str, url: str) -> tuple[str | None, str]:
        settings = await self._get_settings()
        links = dict(settings.social_links or {})
        key_norm = key.lower()
        before = links.get(key_norm)
        links[key_norm] = url
        settings.social_links = links
        await self._session.commit()
        return before, url

    async def get_rules(self) -> ModerationRule | None:
        stmt = select(ModerationRule).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_rule_field(self, field: str, value: str) -> tuple[str, str]:
        rule = await self.get_rules()
        if rule is None:
            settings = await self._get_settings()
            rule = ModerationRule(
                settings_id=settings.id,
                link_posting_policy="",
                allowed_domains=[],
                ad_keywords=[],
                max_mentions=0,
                new_user_probation_duration=0,
                repeated_offense_thresholds={},
            )
            self._session.add(rule)
            await self._session.flush()

        field = field.lower()
        if not hasattr(rule, field):
            raise ValueError(f"Unknown moderation rule field: {field}")

        before = getattr(rule, field)
        parsed = self._parse_rule_value(field, value)
        setattr(rule, field, parsed)
        await self._session.commit()
        after = getattr(rule, field)
        return self._stringify_rule_value(before), self._stringify_rule_value(after)

    async def export_logs(self, days: int) -> list[dict[str, str]]:
        if days <= 0:
            raise ValueError("Days must be a positive integer.")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(UserInfraction)
            .where(UserInfraction.updated_at >= cutoff)
            .order_by(UserInfraction.updated_at.desc())
            .limit(100)
        )
        result = await self._session.execute(stmt)
        entries = []
        for record in result.scalars():
            entries.append(
                {
                    "user_id": str(record.telegram_user_id),
                    "username": record.username or "",
                    "strikes": str(record.strike_count),
                    "updated_at": record.updated_at.isoformat() if record.updated_at else "",
                    "notes": record.notes or "",
                }
            )
        return entries

    @staticmethod
    def _parse_rule_value(field: str, value: str):
        if field in {"allowed_domains", "ad_keywords"}:
            return [item.strip() for item in value.split(",") if item.strip()]
        if field in {"max_mentions", "new_user_probation_duration"}:
            return int(value)
        if field == "repeated_offense_thresholds":
            thresholds: dict[str, int] = {}
            for chunk in value.split(","):
                if "=" in chunk:
                    key, v = chunk.split("=", 1)
                    thresholds[key.strip()] = int(v.strip())
            return thresholds
        return value

    @staticmethod
    def _stringify_rule_value(value) -> str:
        if isinstance(value, dict):
            return ", ".join(f"{k}={v}" for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)
