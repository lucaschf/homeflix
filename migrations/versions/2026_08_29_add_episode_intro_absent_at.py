"""Add episode intro_absent_at column.

Records an operator's verdict that an episode has no opening sequence,
which was previously indistinguishable from "nobody has reviewed it
yet". Nullable with no default, so every existing row starts as
pending — the prior behaviour.

Revision ID: d5b1e8c30a47
Revises: c3a9d4e1f072
Create Date: 2026-08-29 23:30:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d5b1e8c30a47"
down_revision: str | Sequence[str] | None = "c3a9d4e1f072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable intro_absent_at column to episodes."""
    op.add_column(
        "episodes",
        sa.Column("intro_absent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the intro_absent_at column."""
    op.drop_column("episodes", "intro_absent_at")
