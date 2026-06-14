"""Add needs_enrichment_review flag to series.

Mirrors the ``movies`` flag (revision a6b7c8d9e0f1): surfaces series
whose TMDB enrichment couldn't resolve a match, or that an operator
flagged as wrongly enriched, on the admin "needs review" listing. Set
by ``EnrichSeriesMetadataUseCase`` on failure / cleared on success, and
toggled manually via the flag-enrichment command.

``op.add_column`` is used directly (no ``batch_alter_table``) because
rewriting the ``series`` table on SQLite would silently break the
external-content FTS5 link — same discipline as the movies flag.

Revision ID: b1c2d3e4f5a6
Revises: 5f60718293a4
Create Date: 2026-06-14 19:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "5f60718293a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add needs_enrichment_review column + supporting index."""
    op.add_column(
        "series",
        sa.Column(
            "needs_enrichment_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_series_needs_enrichment_review",
        "series",
        ["needs_enrichment_review"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the flag column and its index."""
    op.drop_index("ix_series_needs_enrichment_review", table_name="series")
    op.drop_column("series", "needs_enrichment_review")
