"""Add title column to zealy_members.

Revision ID: 20251027_0005
Revises: 20251026_0004
Create Date: 2025-10-27 00:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251027_0005"
down_revision = "20251026_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("zealy_members", sa.Column("title", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("zealy_members", "title")

