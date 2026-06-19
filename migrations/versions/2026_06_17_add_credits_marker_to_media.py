"""Add credits-marker + detection-state columns to episodes and movies.

Per-file end-credits detection (ADR-021): each episode and movie carries
the onset of its end credits (a flattened ``CreditsMarker`` VO — credits
run to the end, so only ``start_seconds`` is stored) plus an independent
per-file ``credits_detection_state`` lifecycle.

``op.add_column`` is used directly (no ``batch_alter_table``) because
rewriting the ``movies`` table on SQLite would silently drop the
external-content FTS5 link — same discipline as the enrichment-review
flags.

Revision ID: c3d4e5f6a7b8
Revises: f9a0b1c2d3e4
Create Date: 2026-06-17 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "f9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("episodes", "movies")
_MARKER_COLUMNS = (
    ("credits_start_seconds", sa.Integer()),
    ("credits_source", sa.String(length=20)),
    ("credits_confidence", sa.Float()),
    ("credits_detected_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    """Add the nullable marker columns + the non-null state column."""
    for table in _TABLES:
        for name, col_type in _MARKER_COLUMNS:
            op.add_column(table, sa.Column(name, col_type, nullable=True))
        op.add_column(
            table,
            sa.Column(
                "credits_detection_state",
                sa.String(length=30),
                nullable=False,
                server_default="NOT_STARTED",
            ),
        )


def downgrade() -> None:
    """Drop the credits columns from both tables."""
    for table in _TABLES:
        op.drop_column(table, "credits_detection_state")
        for name, _ in _MARKER_COLUMNS:
            op.drop_column(table, name)
