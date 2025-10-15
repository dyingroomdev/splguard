"""Add probation timestamps to user infractions.

Revision ID: 20240505_0002
Revises: 20240504_0001
Create Date: 2024-05-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240505_0002"
down_revision = "20240504_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_infractions",
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_infractions",
        sa.Column("probation_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_infractions", "probation_until")
    op.drop_column("user_infractions", "joined_at")
