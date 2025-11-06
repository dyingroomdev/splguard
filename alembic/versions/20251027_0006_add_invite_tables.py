"""Add invite link tracking tables.

Revision ID: 20251027_0006
Revises: 20251027_0005
Create Date: 2025-10-27 00:06:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251027_0006"
down_revision = "20251027_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("invite_link", sa.String(length=512), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128)),
        sa.Column("creates_join_request", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "invite_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invite_link", sa.String(length=512), nullable=False, index=True),
        sa.Column("joined_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("invite_link", "joined_user_id", name="uq_invite_link_joined_user"),
    )


def downgrade() -> None:
    op.drop_table("invite_stats")
    op.drop_table("invite_links")

