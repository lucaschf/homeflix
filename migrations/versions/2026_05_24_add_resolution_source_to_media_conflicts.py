"""Add resolution_source column to media_conflicts.

Backs ADR-015 Phase 3 — the post-enrich detector silently merges
orphaned candidates (file missing + library root healthy) into the
freshly-enriched winner. The new column distinguishes admin-driven
resolutions (``manual``) from those auto-actions (``auto``) so the
admin UI can split the queue from the audit trail.

Existing resolved rows from Phase 2 are backfilled to ``manual``
(via the column default); they were all created by the admin
``POST /resolve`` endpoint, which is the manual path.

Revision ID: 5f60718293a4
Revises: 4e5f60718293
Create Date: 2026-05-24 09:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "5f60718293a4"
down_revision: str | Sequence[str] | None = "4e5f60718293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``resolution_source`` column and backfill resolved rows."""
    with op.batch_alter_table("media_conflicts") as batch_op:
        batch_op.add_column(
            sa.Column("resolution_source", sa.String(length=20), nullable=True),
        )

    # Backfill: every resolved row prior to this migration came from
    # the manual admin endpoint (Phase 2). Pending rows stay NULL.
    op.execute(
        "UPDATE media_conflicts "
        "SET resolution_source = 'manual' "
        "WHERE resolved_at IS NOT NULL AND resolution_source IS NULL",
    )

    op.create_index(
        "ix_media_conflicts_resolution_source",
        "media_conflicts",
        ["resolution_source"],
    )


def downgrade() -> None:
    """Drop the ``resolution_source`` column."""
    op.drop_index("ix_media_conflicts_resolution_source", table_name="media_conflicts")
    with op.batch_alter_table("media_conflicts") as batch_op:
        batch_op.drop_column("resolution_source")
