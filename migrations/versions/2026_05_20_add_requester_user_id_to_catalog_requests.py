"""Add requester_user_id column to catalog_requests.

The "auto-fulfilled" loop from PR #214 flips a pending request to
fulfilled when the matching title finishes enrichment, but nothing
ties the request back to the user who registered it. Layer B
(in-app notifications) needs that anchor so the "notify on
arrival" ping reaches the correct inbox instead of broadcasting
across the household.

Nullable for backwards compatibility with rows created before the
column existed — those stay anonymous and never produce a
notification.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-05-20 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e0f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``requester_user_id`` column."""
    op.add_column(
        "catalog_requests",
        sa.Column("requester_user_id", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_catalog_requests_requester_user_id",
        "catalog_requests",
        ["requester_user_id"],
    )


def downgrade() -> None:
    """Drop the ``requester_user_id`` column + index."""
    op.drop_index("ix_catalog_requests_requester_user_id", table_name="catalog_requests")
    op.drop_column("catalog_requests", "requester_user_id")
