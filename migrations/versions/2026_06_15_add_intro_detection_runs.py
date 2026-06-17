"""Add intro_detection_runs audit table.

Append-only log written by the intro-detection job: one row per season
processed, with counts, per-episode results (JSON), and the confidence
floor applied — so operators can see why a tick persisted (or dropped)
markers.

Revision ID: f9a0b1c2d3e4
Revises: b1c2d3e4f5a6
Create Date: 2026-06-15 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f9a0b1c2d3e4"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``intro_detection_runs`` table."""
    op.create_table(
        "intro_detection_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("series_id", sa.String(length=50), nullable=False),
        sa.Column(
            "series_title",
            sa.String(length=500),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("season_id", sa.String(length=50), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("algorithm", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("ref_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("analyzed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("persisted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("episode_results", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_intro_detection_runs_external_id",
        "intro_detection_runs",
        ["external_id"],
        unique=True,
    )
    op.create_index("ix_intro_detection_runs_series_id", "intro_detection_runs", ["series_id"])
    op.create_index("ix_intro_detection_runs_season_id", "intro_detection_runs", ["season_id"])
    op.create_index("ix_intro_detection_runs_algorithm", "intro_detection_runs", ["algorithm"])
    op.create_index("ix_intro_detection_runs_outcome", "intro_detection_runs", ["outcome"])
    op.create_index("ix_intro_detection_runs_deleted_at", "intro_detection_runs", ["deleted_at"])


def downgrade() -> None:
    """Drop the ``intro_detection_runs`` table."""
    op.drop_index("ix_intro_detection_runs_deleted_at", table_name="intro_detection_runs")
    op.drop_index("ix_intro_detection_runs_outcome", table_name="intro_detection_runs")
    op.drop_index("ix_intro_detection_runs_algorithm", table_name="intro_detection_runs")
    op.drop_index("ix_intro_detection_runs_season_id", table_name="intro_detection_runs")
    op.drop_index("ix_intro_detection_runs_series_id", table_name="intro_detection_runs")
    op.drop_index("ix_intro_detection_runs_external_id", table_name="intro_detection_runs")
    op.drop_table("intro_detection_runs")
