"""Add last_scan_at column to libraries table.

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-04-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6g7h8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add last_scan_at column."""
    with op.batch_alter_table("libraries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop last_scan_at column."""
    with op.batch_alter_table("libraries", schema=None) as batch_op:
        batch_op.drop_column("last_scan_at")
