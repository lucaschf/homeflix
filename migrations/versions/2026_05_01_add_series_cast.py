"""Add cast column to series.

Series gain the same ``cast`` Text column ``movies`` already carries —
JSON-encoded list of ``{name, profile_path, role, tmdb_id}`` dicts
filled by the TMDB enrichment path. New column is nullable so
existing rows keep loading; the next enrichment pass repopulates
them with the top-billed cast TMDB returns for the series.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-01 09:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``cast`` column to ``series``."""
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cast", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop ``cast`` column from ``series``."""
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_column("cast")
