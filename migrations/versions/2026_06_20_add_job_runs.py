"""Add job_runs execution log.

Generic per-tick execution record for every recurring scheduler job
(thumbnail backfill, intro/credits detection, scheduled scans, dedup
sweep). Backs the admin Jobs dashboard with a uniform "last run /
status / duration / running now" view.

Revision ID: aa11bb22cc33
Revises: e9d8c7b6a5f4
Create Date: 2026-06-20 18:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "aa11bb22cc33"
down_revision: str | Sequence[str] | None = "e9d8c7b6a5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``job_runs`` table."""
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
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
    op.create_index("ix_job_runs_external_id", "job_runs", ["external_id"], unique=True)
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_job_runs_status", "job_runs", ["status"])
    op.create_index("ix_job_runs_deleted_at", "job_runs", ["deleted_at"])


def downgrade() -> None:
    """Drop the ``job_runs`` table."""
    op.drop_index("ix_job_runs_deleted_at", table_name="job_runs")
    op.drop_index("ix_job_runs_status", table_name="job_runs")
    op.drop_index("ix_job_runs_job_id", table_name="job_runs")
    op.drop_index("ix_job_runs_external_id", table_name="job_runs")
    op.drop_table("job_runs")
