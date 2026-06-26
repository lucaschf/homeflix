"""Add localized columns to seasons and episodes.

Stores per-language title/synopsis overrides as a JSON object
(``{lang: {title, synopsis}}``) so season and episode metadata can be
served localized with English fallback — mirroring the existing
``localized`` column on ``movies`` / ``series``. Backfilled by the
series enrich path on the next forced refresh; existing rows stay
``NULL`` until then.

Plain ``add_column`` (additive) — no table recreate, so episode FK
children and indexes are untouched. ``seasons`` / ``episodes`` are not
part of the FTS5 index, so there are no search triggers to rebuild.

Revision ID: b6e4d2a8f1c7
Revises: d8e2f4a6c1b9
Create Date: 2026-06-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e4d2a8f1c7"
down_revision: str | Sequence[str] | None = "d8e2f4a6c1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``localized`` columns to ``seasons`` and ``episodes``."""
    op.add_column("seasons", sa.Column("localized", sa.Text(), nullable=True))
    op.add_column("episodes", sa.Column("localized", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop ``localized`` columns from ``episodes`` and ``seasons``."""
    op.drop_column("episodes", "localized")
    op.drop_column("seasons", "localized")
