"""Add logo_path columns to movies and series.

Stores the URL of the official title logo (transparent PNG hosted by
TMDB) used by hero/detail UIs to render the localized title as an
image instead of plain text. Backfilled by the metadata enrich path
on next refresh; existing rows stay ``NULL`` until then.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-25 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``logo_path`` columns to ``movies`` and ``series``."""
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("logo_path", sa.String(length=1000), nullable=True))
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.add_column(sa.Column("logo_path", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Drop ``logo_path`` columns from ``series`` and ``movies``."""
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_column("logo_path")
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_column("logo_path")
