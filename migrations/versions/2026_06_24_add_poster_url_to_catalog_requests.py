"""Add poster_url snapshot to catalog_requests.

A queued title has no local artwork, so the "Em breve" grid needs a
poster to render. The request now snapshots the TMDB poster URL at
creation (like ``title``). Existing rows are backfilled out-of-band by
``specs/heal_catalog_request_posters.py`` (which calls TMDB) rather than
here — migrations stay network-free.

Revision ID: c4f7a2b9e1d3
Revises: b3e8d1f6a04c
Create Date: 2026-06-24 10:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c4f7a2b9e1d3"
down_revision: str | Sequence[str] | None = "b3e8d1f6a04c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``poster_url`` column."""
    op.add_column(
        "catalog_requests",
        sa.Column("poster_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``poster_url`` column."""
    op.drop_column("catalog_requests", "poster_url")
