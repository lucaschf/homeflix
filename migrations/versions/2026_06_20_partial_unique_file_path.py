"""Make movies/episodes file_path unique only among live rows.

A global UNIQUE(file_path) counted soft-deleted rows, so a soft-deleted
movie (e.g. one promoted to a series) or episode kept its path locked and
a rescan that tried to re-register the same file blew up with an
IntegrityError. Replace the full unique indexes with partial ones scoped
to ``deleted_at IS NULL``.

Uses drop_index/create_index (no table rebuild) so the FTS5 search tables
and their triggers are left untouched.

Revision ID: e9d8c7b6a5f4
Revises: c3d4e5f6a7b8
Create Date: 2026-06-20
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "e9d8c7b6a5f4"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = text("deleted_at IS NULL")


def upgrade() -> None:
    """Swap full unique indexes on file_path for partial (live-only) ones."""
    for table in ("movies", "episodes"):
        index = f"ix_{table}_file_path"
        op.drop_index(index, table_name=table)
        op.create_index(
            index,
            table,
            ["file_path"],
            unique=True,
            sqlite_where=_LIVE,
            postgresql_where=_LIVE,
        )


def downgrade() -> None:
    """Restore the full (all-rows) unique indexes on file_path."""
    for table in ("movies", "episodes"):
        index = f"ix_{table}_file_path"
        op.drop_index(index, table_name=table)
        op.create_index(index, table, ["file_path"], unique=True)
