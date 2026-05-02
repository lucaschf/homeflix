"""Add tagline and collection columns to movies.

``tagline`` is the short marketing line TMDB exposes per movie
(``"In space no one can hear you scream."``). The collection
fields denormalize the franchise the movie belongs to so the
detail page can render a "Part of <name> · N movies" pill
without a separate Collection aggregate. All three columns are
nullable so existing rows keep loading and the next enrichment
pass populates them.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-01 21:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``tagline`` and ``collection_*`` columns to ``movies``."""
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tagline", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("collection_tmdb_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("collection_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("collection_parts_count", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_movies_collection_tmdb_id",
            ["collection_tmdb_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``tagline`` and ``collection_*`` columns from ``movies``."""
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_index("ix_movies_collection_tmdb_id")
        batch_op.drop_column("collection_parts_count")
        batch_op.drop_column("collection_name")
        batch_op.drop_column("collection_tmdb_id")
        batch_op.drop_column("tagline")
