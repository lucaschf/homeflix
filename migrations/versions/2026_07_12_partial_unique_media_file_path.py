"""Make media_files.file_path unique only among live rows.

The partial-unique migration (e9d8c7b6a5f4) scoped movies/episodes
``file_path`` uniqueness to ``deleted_at IS NULL`` but left
``media_files.file_path`` as a full unique index. A soft-deleted variant
therefore kept its path locked, so a rescan re-registering the same file
blew up with an IntegrityError (UNIQUE constraint failed:
media_files.file_path). Replace the full unique index with a partial one,
matching movies/episodes.

Uses drop_index/create_index (no table rebuild) so the FTS5 search tables
and their triggers are left untouched.

Revision ID: a7f3c1e9b2d4
Revises: 5d0b7e1c9a3f
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "a7f3c1e9b2d4"
down_revision: str | None = "5d0b7e1c9a3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = text("deleted_at IS NULL")
_INDEX = "ix_media_files_file_path"


def upgrade() -> None:
    """Swap the full unique index on file_path for a partial (live-only) one."""
    op.drop_index(_INDEX, table_name="media_files")
    op.create_index(
        _INDEX,
        "media_files",
        ["file_path"],
        unique=True,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )


def downgrade() -> None:
    """Restore the full (all-rows) unique index on file_path."""
    op.drop_index(_INDEX, table_name="media_files")
    op.create_index(_INDEX, "media_files", ["file_path"], unique=True)
