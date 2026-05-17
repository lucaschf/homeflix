"""Clean orphan ``media_files`` rows left by FK-less manual deletes.

SQLite ships with foreign-key enforcement OFF by default and the
pragma is *per connection*. Until the companion engine change in
``database.py`` started running ``PRAGMA foreign_keys = ON``, the
declarative ``ON DELETE CASCADE`` on ``media_files.movie_id`` and
``media_files.episode_id`` stayed dormant — a manual
``DELETE FROM movies`` (or ``DELETE FROM episodes``) from an
external tool left orphan ``media_files`` rows behind. Those
orphans then block re-scans because ``media_files.file_path`` has
a ``UNIQUE`` constraint: re-creating the parent row tries to
re-insert the same path and fails.

This migration is a one-shot cleanup. Fresh installs see zero
rows deleted; existing dev DBs (incl. Lucas's where the bug was
first noticed) get healed in place. The pragma fix in
``database.py`` makes sure new orphans can't accumulate from
this point on.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-17 11:00:00.000000

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Delete media_files whose movie_id or episode_id is dangling."""
    bind = op.get_bind()

    movie_orphans = bind.execute(
        sa.text(
            "DELETE FROM media_files "
            "WHERE movie_id IS NOT NULL "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM movies WHERE movies.id = media_files.movie_id"
            "  )"
        )
    ).rowcount

    episode_orphans = bind.execute(
        sa.text(
            "DELETE FROM media_files "
            "WHERE episode_id IS NOT NULL "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM episodes WHERE episodes.id = media_files.episode_id"
            "  )"
        )
    ).rowcount

    if movie_orphans or episode_orphans:
        _logger.info(
            "Cleaned %d orphan media_files (movies side) "
            "and %d orphan media_files (episodes side).",
            movie_orphans,
            episode_orphans,
        )


def downgrade() -> None:
    """No-op — deleted orphans cannot be recovered."""
