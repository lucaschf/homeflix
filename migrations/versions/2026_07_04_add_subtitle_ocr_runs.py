"""Add subtitle_ocr_runs audit table.

Append-only log written by the subtitle-OCR job / manual trigger: one
row per media file with image-based subtitles processed, with per-track
results (JSON) — so operators can see which titles were processed and
what was extracted (ADR-027).

Revision ID: 5d0b7e1c9a3f
Revises: c4a9e7b1d6f3
Create Date: 2026-07-04 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "5d0b7e1c9a3f"
down_revision: str | Sequence[str] | None = "c4a9e7b1d6f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``subtitle_ocr_runs`` table."""
    op.create_table(
        "subtitle_ocr_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("media_kind", sa.String(length=20), nullable=False),
        sa.Column("media_id", sa.String(length=50), nullable=False),
        sa.Column(
            "media_title",
            sa.String(length=500),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("image_track_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("extracted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("track_results", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
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
        "ix_subtitle_ocr_runs_external_id",
        "subtitle_ocr_runs",
        ["external_id"],
        unique=True,
    )
    op.create_index("ix_subtitle_ocr_runs_media_kind", "subtitle_ocr_runs", ["media_kind"])
    op.create_index("ix_subtitle_ocr_runs_media_id", "subtitle_ocr_runs", ["media_id"])
    op.create_index("ix_subtitle_ocr_runs_outcome", "subtitle_ocr_runs", ["outcome"])
    op.create_index("ix_subtitle_ocr_runs_deleted_at", "subtitle_ocr_runs", ["deleted_at"])


def downgrade() -> None:
    """Drop the ``subtitle_ocr_runs`` table."""
    op.drop_index("ix_subtitle_ocr_runs_deleted_at", table_name="subtitle_ocr_runs")
    op.drop_index("ix_subtitle_ocr_runs_outcome", table_name="subtitle_ocr_runs")
    op.drop_index("ix_subtitle_ocr_runs_media_id", table_name="subtitle_ocr_runs")
    op.drop_index("ix_subtitle_ocr_runs_media_kind", table_name="subtitle_ocr_runs")
    op.drop_index("ix_subtitle_ocr_runs_external_id", table_name="subtitle_ocr_runs")
    op.drop_table("subtitle_ocr_runs")
