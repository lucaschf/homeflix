"""Add subtitle text-edge column to preferences (2.4 follow-up).

Adds a per-profile subtitle text-edge style (``none`` / ``shadow`` /
``outline``) the player's overlay maps to a CSS treatment. Defaults to
``shadow`` so existing rows keep the current soft-shadow look unchanged.

Revision ID: c3a9d4e1f072
Revises: b2f1c8a4e6d3
Create Date: 2026-08-16 21:30:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c3a9d4e1f072"
down_revision: str | Sequence[str] | None = "b2f1c8a4e6d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the subtitle text-edge column with the shadow default."""
    op.add_column(
        "preferences",
        sa.Column("subtitle_text_edge", sa.String(10), nullable=False, server_default="shadow"),
    )


def downgrade() -> None:
    """Drop the subtitle text-edge column."""
    op.drop_column("preferences", "subtitle_text_edge")
