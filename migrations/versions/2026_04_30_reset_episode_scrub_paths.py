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
2. Walk every configured library path and best-effort delete the
   legacy ``.homeflix/thumbnails/sprite.jpg`` and ``sprite.vtt`` files
   sitting directly under that subfolder (i.e. NOT inside a per-stem
   leaf — those are the new layout's sprites and must stay). Failures
   are swallowed because filesystem cleanup is housekeeping, not data
   integrity, and we do not want a missing path or a permission
   glitch to abort the schema migration.

Movies are intentionally not reset. The new per-stem layout means a
movie's existing sprite still lives at the path the DB column
remembers, so they stay served until the file is rescanned for some
other reason.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-04-30 22:00:00.000000

"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    """Walk every library root and prune legacy sprite files.

    Best-effort: any IO error is logged at WARNING and the migration
    keeps going.
    """
    roots = list(_collect_library_roots())
    seen_dirs: set[Path] = set()
    deleted = 0
    for root in roots:
        deleted += _prune_legacy_under(root, seen_dirs)
    if deleted:
        _logger.info("Removed %d legacy sprite file(s) from disk", deleted)


def _collect_library_roots() -> list[Path]:
    """Return existing directories from ``libraries.paths`` JSON arrays."""
    conn = op.get_bind()
    try:
        rows = conn.execute(
            sa.text("SELECT paths FROM libraries WHERE deleted_at IS NULL"),
        ).fetchall()
    except sa.exc.SQLAlchemyError as exc:
        _logger.warning("Skipping legacy sprite cleanup; query failed: %s", exc)
        return []

    roots: list[Path] = []
    for row in rows:
        paths_json = row[0]
        if not paths_json:
            continue
        try:
            library_paths = json.loads(paths_json)
        except (TypeError, ValueError):
            continue
        for raw in library_paths:
            try:
                root = Path(raw).resolve()
            except OSError:
                continue
            if root.is_dir():
                roots.append(root)
    return roots


def _prune_legacy_under(root: Path, seen_dirs: set[Path]) -> int:
    """Delete legacy sprite files inside one library root."""
    deleted = 0
    for legacy_dir in root.rglob(_LEGACY_SPRITE_RELATIVE_DIR.name):
        # ``rglob`` returns every directory named ``thumbnails``; only
        # the ones whose parent is the ``.homeflix`` marker belong to
        # this app's layout.
        if legacy_dir.parent.name != _LEGACY_SPRITE_RELATIVE_DIR.parts[0]:
            continue
        if legacy_dir in seen_dirs:
            continue
        seen_dirs.add(legacy_dir)
        for filename in _LEGACY_FILES:
            target = legacy_dir / filename
            try:
                target.unlink(missing_ok=True)
                deleted += 1
            except OSError as exc:
                _logger.warning("Could not delete legacy sprite %s: %s", target, exc)
    return deleted
