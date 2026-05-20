"""Add title column to catalog_requests.

The admin queue page only had ``tmdb/<id>`` to identify each pending
request — fine when the operator recognizes the id, painful when
they don't. Snapshotting the title at request time lets the queue
table render "Title (tmdb/123)" without a TMDB round-trip on every
listing. Existing rows keep ``NULL`` and the admin UI falls back to
the bare id.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-19 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``title`` column."""
    op.add_column(
        "catalog_requests",
        sa.Column("title", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``title`` column."""
    op.drop_column("catalog_requests", "title")
