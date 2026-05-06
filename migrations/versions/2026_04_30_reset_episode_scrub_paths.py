"""Reset episode scrub-preview paths and clean up legacy sprite files.

The thumbnail backfill job used to write every generated sprite into
``<media_parent>/.homeflix/thumbnails/sprite.{jpg,vtt}``. For movies
this was fine because each movie usually sits in its own folder, but
every episode of a TV season shares the season directory, so the
sprite kept getting overwritten and every episode's persisted
``scrub_preview_path`` ended up pointing at the same file (which
contained the tiles of whichever episode was generated last).

The fix nests the output under a per-file-stem subfolder. This
migration drains the broken state so the backfill can repopulate
from scratch:

1. ``UPDATE episodes SET scrub_preview_path = NULL`` so every episode
   re-enters ``find_episodes_missing_scrub_preview`` and gets a fresh
   sprite at the new layout.
2. Best-effort delete the legacy ``.homeflix/thumbnails/sprite.jpg``
   and ``sprite.vtt`` files that were sitting directly under each
   season directory. The candidate directories are derived from the
   ``media_files`` rows tied to episodes — we only touch parents we
   know hosted an episode file, never recursively scan a library
   tree. Failures are swallowed: filesystem cleanup is housekeeping,
   not data integrity, and we never want a missing path or a
   permission glitch to abort the schema migration.

Movies are intentionally not reset. The new per-stem layout means a
movie's existing sprite still lives at the path the DB column
remembers, so they stay served until the file is rescanned for some
other reason.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-04-30 22:00:00.000000

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_logger = logging.getLogger(__name__)

_LEGACY_SPRITE_RELATIVE_DIR = Path(".homeflix") / "thumbnails"
_LEGACY_FILES = ("sprite.jpg", "sprite.vtt")


def upgrade() -> None:
    """Null episode scrub paths and best-effort prune legacy sprites."""
    op.execute("UPDATE episodes SET scrub_preview_path = NULL")
    _delete_legacy_sprite_files()


def downgrade() -> None:
    """Schema downgrade is a no-op.

    The data lost here was already incorrect (every episode pointed
    at the same overwritten sprite), and the backfill job repopulates
    ``scrub_preview_path`` on its own.
    """


def _delete_legacy_sprite_files() -> None:
    """Prune the bug's legacy sprite files across every season directory."""
    deleted = 0
    for legacy_dir in _legacy_dirs_for_episodes():
        for filename in _LEGACY_FILES:
            target = legacy_dir / filename
            if not target.is_file():
                continue
            try:
                target.unlink()
                deleted += 1
            except OSError as exc:
                _logger.warning("Could not delete legacy sprite %s: %s", target, exc)
    if deleted:
        _logger.info("Removed %d legacy sprite file(s) from disk", deleted)


def _legacy_dirs_for_episodes() -> Iterator[Path]:
    """Yield each unique legacy ``.homeflix/thumbnails`` dir under an episode parent.

    Drives off ``media_files`` rows whose ``episode_id`` is set, so we
    visit exactly the season directories that were affected by the
    bug instead of recursively scanning a (potentially huge) library
    tree. Yields each candidate at most once and only when the
    directory actually exists on disk.
    """
    conn = op.get_bind()
    try:
        rows = conn.execute(
            sa.text(
                "SELECT DISTINCT file_path FROM media_files WHERE episode_id IS NOT NULL",
            ),
        ).fetchall()
    except sa.exc.SQLAlchemyError as exc:
        _logger.warning("Skipping legacy sprite cleanup; query failed: %s", exc)
        return

    seen: set[Path] = set()
    for row in rows:
        file_path = row[0]
        if not file_path:
            continue
        legacy_dir = Path(file_path).parent / _LEGACY_SPRITE_RELATIVE_DIR
        if legacy_dir in seen:
            continue
        seen.add(legacy_dir)
        if legacy_dir.is_dir():
            yield legacy_dir
