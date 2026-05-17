"""Add needs_enrichment_review flag to movies.

Used by the admin "needs review" listing to surface movies whose
TMDB enrichment couldn't resolve a match (off-year title, cross-type
miss, ambiguous folder). The flag is set by ``EnrichMovieMetadataUseCase``
on failure and cleared on success.

``op.add_column`` is used directly (no ``batch_alter_table``)
because rewriting the ``movies`` table on SQLite would silently
break the external-content FTS5 link — same rationale as the
2026-04-14 catch-up migration that introduced this discipline.

Revision ID: a6b7c8d9e0f1
Revises: f4a5b6c7d8e9
Create Date: 2026-05-17 09:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "a6b7c8d9e0f1"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add needs_enrichment_review column + supporting index."""
    op.add_column(
        "movies",
        sa.Column(
            "needs_enrichment_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_movies_needs_enrichment_review",
        "movies",
        ["needs_enrichment_review"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the flag column and its index."""
    op.drop_index("ix_movies_needs_enrichment_review", table_name="movies")
    op.drop_column("movies", "needs_enrichment_review")
