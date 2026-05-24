"""Add winner_id column to media_conflicts.

Backs ADR-015 Phase 2 — the resolve endpoint persists which side
survived for MERGE actions so the admin queue can render audit
trail entries ("merged into mov_xxx") without joining onto the
soft-deleted loser row.

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
Create Date: 2026-05-23 17:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "4e5f60718293"
down_revision: str | Sequence[str] | None = "3d4e5f607182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``winner_id`` column."""
    with op.batch_alter_table("media_conflicts") as batch_op:
        batch_op.add_column(sa.Column("winner_id", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Drop the ``winner_id`` column."""
    with op.batch_alter_table("media_conflicts") as batch_op:
        batch_op.drop_column("winner_id")
