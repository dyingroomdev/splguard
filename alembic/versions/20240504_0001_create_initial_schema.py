"""Create initial schema for core models.

Revision ID: 20240504_0001
Revises: 
Create Date: 2024-05-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20240504_0001"
down_revision = None
branch_labels = None
depends_on = None


presale_status = sa.Enum("upcoming", "active", "ended", name="presale_status")


def upgrade() -> None:
    presale_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("token_ticker", sa.String(length=32), nullable=False),
        sa.Column("contract_addresses", postgresql.ARRAY(sa.String(length=128)), nullable=False),
        sa.Column("explorer_url", sa.String(length=512), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("docs", sa.String(length=512), nullable=True),
        sa.Column(
            "social_links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("logo", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "moderation_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("settings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_posting_policy", sa.Text(), nullable=False),
        sa.Column(
            "allowed_domains",
            postgresql.ARRAY(sa.String(length=255)),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "ad_keywords",
            postgresql.ARRAY(sa.String(length=255)),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("max_mentions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new_user_probation_duration", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "repeated_offense_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "presales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("settings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            presale_status,
            nullable=False,
            server_default="upcoming",
        ),
        sa.Column("platform", sa.String(length=255), nullable=True),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("hardcap", sa.Numeric(18, 2), nullable=True),
        sa.Column("softcap", sa.Numeric(18, 2), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raised_so_far", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "faqs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("settings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=False),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "user_infractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("settings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_trusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_muted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ban_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("strike_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_infractions_telegram_user_id",
        "user_infractions",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_infractions_telegram_user_id", table_name="user_infractions")
    op.drop_table("user_infractions")
    op.drop_table("team_members")
    op.drop_table("presales")
    op.drop_table("moderation_rules")
    op.drop_table("settings")
    presale_status.drop(op.get_bind(), checkfirst=True)
