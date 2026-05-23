"""Create media_conflicts table.

Backs ADR-015 Phase 1 — the post-enrich detection hook materialises
content-identity collisions (two media entities sharing a TMDB id or
matching the title+year fallback) as rows in this table for the
operator to resolve via the admin queue.

The schema is polymorphic from day one: ``candidate_*_type`` is a
discriminator (``"movie"`` in Phase 1, ``"series"`` later) so adding
Series support later does not require a table change.

No unique constraint on the candidate pair — Mark As Distinct
semantics that suppress re-flagging belong to a future "blocked
pairs" table; pending-pair deduplication is enforced at query time by
``find_pending_by_pair`` in the repository.

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-05-23 14:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "3d4e5f607182"
down_revision: str | Sequence[str] | None = "2c3d4e5f6071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``media_conflicts`` table."""
    op.create_table(
        "media_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("candidate_a_id", sa.String(length=50), nullable=False),
        sa.Column("candidate_a_type", sa.String(length=20), nullable=False),
        sa.Column("candidate_b_id", sa.String(length=50), nullable=False),
        sa.Column("candidate_b_type", sa.String(length=20), nullable=False),
        sa.Column("match_reason", sa.String(length=30), nullable=False),
        sa.Column("runtime_delta_minutes", sa.Float(), nullable=True),
        sa.Column("suggested_action", sa.String(length=30), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_media_conflicts_external_id",
        "media_conflicts",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_media_conflicts_candidate_a_id",
        "media_conflicts",
        ["candidate_a_id"],
    )
    op.create_index(
        "ix_media_conflicts_candidate_b_id",
        "media_conflicts",
        ["candidate_b_id"],
    )
    op.create_index(
        "ix_media_conflicts_resolved_at",
        "media_conflicts",
        ["resolved_at"],
    )
    op.create_index(
        "ix_media_conflicts_deleted_at",
        "media_conflicts",
        ["deleted_at"],
    )


def downgrade() -> None:
    """Drop the ``media_conflicts`` table."""
    op.drop_index("ix_media_conflicts_deleted_at", table_name="media_conflicts")
    op.drop_index("ix_media_conflicts_resolved_at", table_name="media_conflicts")
    op.drop_index("ix_media_conflicts_candidate_b_id", table_name="media_conflicts")
    op.drop_index("ix_media_conflicts_candidate_a_id", table_name="media_conflicts")
    op.drop_index("ix_media_conflicts_external_id", table_name="media_conflicts")
    op.drop_table("media_conflicts")
