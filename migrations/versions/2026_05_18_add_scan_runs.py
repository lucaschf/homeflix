"""Create scan_runs table.

Backs the admin scan + bulk-enrich history page. A single table
handles both kinds (discriminated by ``kind``) and both trigger
sources (admin-initiated ``manual`` vs scheduler ``scheduled``).
Per-kind counters live in the ``summary`` JSON column to avoid a
wide table where half the columns are null for whichever kind
didn't run.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-18 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``scan_runs`` table."""
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("library_id", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
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
        "ix_scan_runs_external_id",
        "scan_runs",
        ["external_id"],
        unique=True,
    )
    op.create_index("ix_scan_runs_kind", "scan_runs", ["kind"], unique=False)
    op.create_index("ix_scan_runs_trigger", "scan_runs", ["trigger"], unique=False)
    op.create_index(
        "ix_scan_runs_library_id",
        "scan_runs",
        ["library_id"],
        unique=False,
    )
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"], unique=False)
    op.create_index(
        "ix_scan_runs_deleted_at",
        "scan_runs",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ``scan_runs`` table."""
    op.drop_index("ix_scan_runs_deleted_at", table_name="scan_runs")
    op.drop_index("ix_scan_runs_status", table_name="scan_runs")
    op.drop_index("ix_scan_runs_library_id", table_name="scan_runs")
    op.drop_index("ix_scan_runs_trigger", table_name="scan_runs")
    op.drop_index("ix_scan_runs_kind", table_name="scan_runs")
    op.drop_index("ix_scan_runs_external_id", table_name="scan_runs")
    op.drop_table("scan_runs")
