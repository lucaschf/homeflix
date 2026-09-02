"""Add per-profile intro / credits skip modes to preferences.

Both columns default to ``manual`` — today's behaviour, where the
player only offers a button — so existing profiles are untouched until
someone opts into auto-skip.

Revision ID: f1a6d0c72e93
Revises: d5b1e8c30a47
Create Date: 2026-09-02 15:30:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f1a6d0c72e93"
down_revision: str | Sequence[str] | None = "d5b1e8c30a47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the skip-mode columns, defaulting existing rows to manual."""
    op.add_column(
        "preferences",
        sa.Column("intro_skip_mode", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "preferences",
        sa.Column("credits_skip_mode", sa.String(20), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    """Drop the skip-mode columns."""
    op.drop_column("preferences", "credits_skip_mode")
    op.drop_column("preferences", "intro_skip_mode")
