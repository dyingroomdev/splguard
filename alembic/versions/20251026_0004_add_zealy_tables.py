"""Add Zealy tables for members, quests, and grants.

Revision ID: 20251026_0004
Revises: 20251024_0003_add_bio_to_team_members
Create Date: 2025-10-26 00:04:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251026_0004"
down_revision = "20251024_0003"
branch_labels = None
depends_on = None


zealy_grant_status = sa.Enum(
    "pending",
    "completed",
    "failed",
    name="zealy_grant_status",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "zealy_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("wallet", sa.String(length=255), unique=True),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tier", sa.String(length=64)),
        sa.Column("zealy_user_id", sa.String(length=128), unique=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "zealy_quests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
        sa.Column("zealy_quest_id", sa.String(length=128), unique=True),
        sa.Column("xp_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "zealy_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("zealy_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quest_id", sa.Integer(), sa.ForeignKey("zealy_quests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", zealy_grant_status, nullable=False, server_default="pending"),
        sa.Column("tx_ref", sa.String(length=255)),
        sa.Column("xp_awarded", sa.Integer()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("member_id", "quest_id", name="uq_zealy_grant_member_quest"),
    )


def downgrade() -> None:
    op.drop_table("zealy_grants")
    op.drop_table("zealy_quests")
    op.drop_table("zealy_members")
    zealy_grant_status.drop(op.get_bind(), checkfirst=False)
