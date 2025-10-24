"""Add bio field to team_members table.

Revision ID: 20251024_0003
Revises: 20240505_0002
Create Date: 2025-10-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251024_0003"
down_revision = "20240505_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add bio column to team_members table
    op.add_column("team_members", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove bio column from team_members table
    op.drop_column("team_members", "bio")
