"""Add media-file time segments for multi-episode files (ADR-030).

A single physical file can hold several titles (e.g. an old mini-series with
two episodes concatenated in one ``.mkv``). To model that, ``media_files``
gains an optional ``[start, end)`` time window and the global uniqueness of
``file_path`` is relaxed to per-``(path, segment)``:

- ``start_offset_seconds`` / ``end_offset_seconds`` — NULL for a whole-file
  variant (the default, backward-compatible case), or the title's window
  within a shared file.
- ``ix_media_files_file_path`` drops its UNIQUE flag (kept as a plain lookup
  index); a new ``ux_media_file_path_segment`` enforces uniqueness on
  ``(file_path, COALESCE(start,-1), COALESCE(end,-1))`` so whole-file
  duplicates are still rejected while disjoint segments of one file coexist.
- ``ix_episodes_file_path`` drops its UNIQUE flag for the same reason: two
  live episodes may now share the same denormalized primary-file path.

Revision ID: 7f3a2b9c4d10
Revises: 3c7f2a9d1b46
Create Date: 2026-08-09 18:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "7f3a2b9c4d10"
down_revision: str | Sequence[str] | None = "3c7f2a9d1b46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = text("deleted_at IS NULL")
_SEG_START = sa.text("COALESCE(start_offset_seconds, -1)")
_SEG_END = sa.text("COALESCE(end_offset_seconds, -1)")


def upgrade() -> None:
    """Add segment columns and relax file_path uniqueness to per-segment."""
    op.add_column(
        "media_files",
        sa.Column("start_offset_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "media_files",
        sa.Column("end_offset_seconds", sa.Integer(), nullable=True),
    )

    # Swap the global-unique path index for a plain lookup index...
    op.drop_index("ix_media_files_file_path", table_name="media_files")
    op.create_index(
        "ix_media_files_file_path",
        "media_files",
        ["file_path"],
        unique=False,
    )
    # ...and enforce uniqueness per (path, segment) instead. COALESCE gives
    # whole-file rows (NULL offsets) a concrete key so duplicates are caught.
    op.create_index(
        "ux_media_file_path_segment",
        "media_files",
        ["file_path", _SEG_START, _SEG_END],
        unique=True,
    )

    # Episodes may now share a physical file, so the denormalized flat
    # ``file_path`` is no longer unique — keep the partial index for lookups.
    op.drop_index("ix_episodes_file_path", table_name="episodes")
    op.create_index(
        "ix_episodes_file_path",
        "episodes",
        ["file_path"],
        unique=False,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )


def downgrade() -> None:
    """Restore global path uniqueness and drop segment columns.

    NOTE: this fails if the data now contains multi-episode files (shared
    ``file_path`` rows), which is expected — you cannot downgrade past data
    that depends on the new model.
    """
    op.drop_index("ix_episodes_file_path", table_name="episodes")
    op.create_index(
        "ix_episodes_file_path",
        "episodes",
        ["file_path"],
        unique=True,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )

    op.drop_index("ux_media_file_path_segment", table_name="media_files")
    op.drop_index("ix_media_files_file_path", table_name="media_files")
    op.create_index(
        "ix_media_files_file_path",
        "media_files",
        ["file_path"],
        unique=True,
    )

    op.drop_column("media_files", "end_offset_seconds")
    op.drop_column("media_files", "start_offset_seconds")
