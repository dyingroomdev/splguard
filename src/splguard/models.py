from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class PresaleStatus(enum.Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDED = "ended"


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_addresses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    explorer_url: Mapped[Optional[str]] = mapped_column(String(512))
    website: Mapped[Optional[str]] = mapped_column(String(512))
    docs: Mapped[Optional[str]] = mapped_column(String(512))
    social_links: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    logo: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    team_members: Mapped[list["TeamMember"]] = relationship(
        back_populates="settings", cascade="all, delete-orphan"
    )
    presales: Mapped[list["Presale"]] = relationship(
        back_populates="settings", cascade="all, delete-orphan"
    )
    moderation_rules: Mapped[list["ModerationRule"]] = relationship(
        back_populates="settings", cascade="all, delete-orphan"
    )
    infra_entries: Mapped[list["UserInfraction"]] = relationship(
        back_populates="settings", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_id: Mapped[int] = mapped_column(ForeignKey("settings.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    settings: Mapped[Settings] = relationship(back_populates="team_members")


class Presale(Base):
    __tablename__ = "presales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_id: Mapped[int] = mapped_column(ForeignKey("settings.id", ondelete="CASCADE"))
    status: Mapped[PresaleStatus] = mapped_column(
        Enum(PresaleStatus, name="presale_status", native_enum=False),
        default=PresaleStatus.UPCOMING,
        nullable=False,
    )
    platform: Mapped[Optional[str]] = mapped_column(String(255))
    links: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hardcap: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    softcap: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    raised_so_far: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    faqs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    settings: Mapped[Settings] = relationship(back_populates="presales")


class ModerationRule(Base):
    __tablename__ = "moderation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_id: Mapped[int] = mapped_column(ForeignKey("settings.id", ondelete="CASCADE"))
    link_posting_policy: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ad_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    max_mentions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_user_probation_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repeated_offense_thresholds: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    settings: Mapped[Settings] = relationship(back_populates="moderation_rules")


class UserInfraction(Base):
    __tablename__ = "user_infractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_id: Mapped[int] = mapped_column(ForeignKey("settings.id", ondelete="CASCADE"))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_trusted: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_muted: Mapped[bool] = mapped_column(default=False, nullable=False)
    muted_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ban_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    strike_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    probation_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    settings: Mapped[Settings] = relationship(back_populates="infra_entries")


class ZealyMember(Base):
    __tablename__ = "zealy_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    wallet: Mapped[str | None] = mapped_column(String(255), unique=True)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tier: Mapped[str | None] = mapped_column(String(64))
    zealy_user_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    grants: Mapped[list["ZealyGrant"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class ZealyQuest(Base):
    __tablename__ = "zealy_quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    zealy_quest_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    xp_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    grants: Mapped[list["ZealyGrant"]] = relationship(
        back_populates="quest", cascade="all, delete-orphan"
    )


class ZealyGrantStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ZealyGrant(Base):
    __tablename__ = "zealy_grants"
    __table_args__ = (
        UniqueConstraint("member_id", "quest_id", name="uq_zealy_grant_member_quest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("zealy_members.id", ondelete="CASCADE"))
    quest_id: Mapped[int] = mapped_column(ForeignKey("zealy_quests.id", ondelete="CASCADE"))
    status: Mapped[ZealyGrantStatus] = mapped_column(
        Enum(ZealyGrantStatus, name="zealy_grant_status", native_enum=False),
        default=ZealyGrantStatus.PENDING,
        nullable=False,
    )
    tx_ref: Mapped[str | None] = mapped_column(String(255))
    xp_awarded: Mapped[int | None] = mapped_column(Integer)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    member: Mapped[ZealyMember] = relationship(back_populates="grants")
    quest: Mapped[ZealyQuest] = relationship(back_populates="grants")
