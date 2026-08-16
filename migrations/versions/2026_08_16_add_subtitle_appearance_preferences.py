"""Add subtitle-appearance columns to preferences (2.4 Subtitle Appearance).

Per-profile subtitle styling the player's overlay reads — account-level and
synced across devices, mirroring how streaming services persist caption
style. Three columns are added to ``preferences`` with the white-on-dim
defaults so existing rows keep working unchanged:

- ``subtitle_color`` — text color (CSS color), default ``#FFFFFF``.
- ``subtitle_background`` — background color (CSS color), default
  ``rgba(0, 0, 0, 0.75)``.
- ``subtitle_font_size`` — relative size tier (``small`` / ``medium`` /
  ``large``), default ``medium``.

Revision ID: b2f1c8a4e6d3
Revises: 7f3a2b9c4d10
Create Date: 2026-08-16 20:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b2f1c8a4e6d3"
down_revision: str | Sequence[str] | None = "7f3a2b9c4d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the three subtitle-appearance columns with defaults."""
    op.add_column(
        "preferences",
        sa.Column("subtitle_color", sa.String(32), nullable=False, server_default="#FFFFFF"),
    )
    op.add_column(
        "preferences",
        sa.Column(
            "subtitle_background",
            sa.String(32),
            nullable=False,
            server_default="rgba(0, 0, 0, 0.75)",
        ),
    )
    op.add_column(
        "preferences",
        sa.Column("subtitle_font_size", sa.String(10), nullable=False, server_default="medium"),
    )


def downgrade() -> None:
    """Drop the subtitle-appearance columns."""
    op.drop_column("preferences", "subtitle_font_size")
    op.drop_column("preferences", "subtitle_background")
    op.drop_column("preferences", "subtitle_color")
