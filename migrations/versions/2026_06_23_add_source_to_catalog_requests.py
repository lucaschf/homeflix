"""Add source (user/household) to catalog_requests + backfill.

ADR-022 records where a request originated: a member asking for the
title (``user``) vs. the household/system seeding it (``household``).
The backfill derives it from the existing requester anchor — a known
``requester_user_id`` means a member asked, so those rows become
``user``; the rest stay ``household``.

Revision ID: b3e8d1f6a04c
Revises: 7a1c93b5e2d8
Create Date: 2026-06-23 19:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b3e8d1f6a04c"
down_revision: str | Sequence[str] | None = "7a1c93b5e2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``source`` column and backfill from ``requester_user_id``."""
    # Plain add_column (no batch) — catalog_requests isn't an FTS table,
    # so there are no triggers to preserve. NOT NULL with a server
    # default so existing rows land on ``household`` before the backfill
    # promotes the member-originated ones.
    op.add_column(
        "catalog_requests",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="household",
        ),
    )
    op.get_bind().execute(
        text(
            "UPDATE catalog_requests " "SET source = 'user' " "WHERE requester_user_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    """Drop the ``source`` column."""
    op.drop_column("catalog_requests", "source")
