"""Add localized_titles column to catalog_requests.

Stores a per-language title snapshot (``{lang: title}``) resolved once
from TMDB when a request is first created, so the "Em breve" feed and
admin queue can render titles in the viewer's language with English
fallback. Backfilled on the next request creation/reconcile; existing
rows stay ``NULL`` and fall back to the plain ``title`` snapshot.

Plain ``add_column`` (additive) — no table recreate; ``catalog_requests``
is not part of the FTS5 index, so there are no search triggers to rebuild.

Revision ID: c4a9e7b1d6f3
Revises: b6e4d2a8f1c7
Create Date: 2026-06-26 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a9e7b1d6f3"
down_revision: str | Sequence[str] | None = "b6e4d2a8f1c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``localized_titles`` column to ``catalog_requests``."""
    op.add_column("catalog_requests", sa.Column("localized_titles", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the ``localized_titles`` column from ``catalog_requests``."""
    op.drop_column("catalog_requests", "localized_titles")
