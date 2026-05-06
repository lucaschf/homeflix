"""Add library_id to movies and series, backfilled by file-path matching.

Per ADR-010 + the per-profile rollout, the catalog needs to be
filterable per-profile via ``Profile.allowed_library_ids``. That
filter has nowhere to land today because Movie/Series have no
foreign reference to their owning Library — the relationship is
implicit (the scanner happens to write paths under directories that
match a library's configured paths).

This migration materialises the relationship as a plain string column
on both ``movies`` and ``series`` (no FK because the catalog and
library tables live in different bounded contexts and ADR-008
forbids cross-BC FKs).

Sequence (so existing dev data survives):

1. ADD COLUMN library_id NULLABLE on both tables.
2. Backfill per-row by matching each movie's ``file_path`` (or each
   series' first episode's file_path) against every library's
   ``paths`` JSON array. First library whose path is a prefix of
   the file path wins. Orphans (rows whose file_path matches no
   library) abort the migration with a clear message — manual
   intervention beats persisting NULLs that would later violate the
   NOT NULL alteration.
3. ALTER COLUMN library_id NOT NULL.

Revision ID: b09c1d2e3f4a
Revises: e7f8a9b0c1d2
Create Date: 2026-05-04 09:00:00.000000

"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b09c1d2e3f4a"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load_libraries(connection: sa.Connection) -> list[tuple[str, list[str]]]:
    """Return ``[(library_external_id, [path1, path2, ...]), ...]``.

    Excludes soft-deleted libraries — backfilling against a deleted
    library would silently re-attach catalog rows to data the
    operator chose to retire.
    """
    rows = connection.execute(
        sa.text(
            "SELECT external_id, paths FROM libraries "
            "WHERE deleted_at IS NULL "
            "ORDER BY created_at ASC"
        )
    ).fetchall()
    libraries: list[tuple[str, list[str]]] = []
    for external_id, paths_json in rows:
        try:
            paths = json.loads(paths_json) if paths_json else []
        except (TypeError, ValueError) as exc:
            msg = f"Library {external_id} has malformed paths JSON: {paths_json!r}"
            raise RuntimeError(msg) from exc
        libraries.append((external_id, list(paths)))
    return libraries


def _match_library(
    file_path: str | None,
    libraries: list[tuple[str, list[str]]],
) -> str | None:
    """Return the first library whose path is a prefix of ``file_path``.

    Path matching uses naive prefix comparison after normalising
    trailing slashes — the catalog runs on whatever filesystem the
    operator scans, and SQLite stores raw strings, so we don't try
    to be platform-clever here. ``None`` for ``file_path`` always
    returns ``None`` (no anchor to match against).
    """
    if file_path is None:
        return None
    for library_id, paths in libraries:
        for raw_path in paths:
            anchor = raw_path.rstrip("/").rstrip("\\")
            if (
                file_path == anchor
                or file_path.startswith(anchor + "/")
                or file_path.startswith(anchor + "\\")
            ):
                return library_id
    return None


def _series_anchor_path(connection: sa.Connection, series_id: int) -> str | None:
    """Return any episode file_path under ``series_id``, or ``None``.

    The earliest-recorded episode is the most stable choice — newer
    episodes can be added after the series gets its library_id, so
    using the first-seen one keeps backfills deterministic across
    re-runs.
    """
    row = connection.execute(
        sa.text(
            "SELECT e.file_path "
            "FROM episodes e "
            "JOIN seasons sn ON sn.id = e.season_id "
            "WHERE sn.series_id = :series_id "
            "  AND e.file_path IS NOT NULL "
            "  AND e.deleted_at IS NULL "
            "ORDER BY e.created_at ASC "
            "LIMIT 1"
        ),
        {"series_id": series_id},
    ).first()
    return row[0] if row else None


def _backfill_movies(
    connection: sa.Connection,
    libraries: list[tuple[str, list[str]]],
) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT id, external_id, file_path "
            "FROM movies "
            "WHERE library_id IS NULL "
            "  AND deleted_at IS NULL"
        )
    ).fetchall()
    orphans: list[str] = []
    for movie_id, external_id, file_path in rows:
        match = _match_library(file_path, libraries)
        if match is None:
            orphans.append(f"{external_id} (file_path={file_path!r})")
            continue
        connection.execute(
            sa.text("UPDATE movies SET library_id = :lid WHERE id = :mid"),
            {"lid": match, "mid": movie_id},
        )
    if orphans:
        msg = (
            "Cannot backfill movies.library_id: the following movies are "
            "not under any active library's configured paths. Either "
            "register a library that owns them or soft-delete the rows "
            "before re-running the migration:\n  - " + "\n  - ".join(orphans)
        )
        raise RuntimeError(msg)


def _backfill_series(
    connection: sa.Connection,
    libraries: list[tuple[str, list[str]]],
) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT id, external_id "
            "FROM series "
            "WHERE library_id IS NULL "
            "  AND deleted_at IS NULL"
        )
    ).fetchall()
    orphans: list[str] = []
    for series_id, external_id in rows:
        anchor = _series_anchor_path(connection, series_id)
        match = _match_library(anchor, libraries)
        if match is None:
            orphans.append(
                f"{external_id} (anchor_episode_path={anchor!r})"
                if anchor
                else f"{external_id} (no episodes with file_path yet)"
            )
            continue
        connection.execute(
            sa.text("UPDATE series SET library_id = :lid WHERE id = :sid"),
            {"lid": match, "sid": series_id},
        )
    if orphans:
        msg = (
            "Cannot backfill series.library_id: the following series have "
            "no episodes whose file_path is under any active library. "
            "Either register a library that owns them, scan to populate "
            "episode paths, or soft-delete the rows before re-running "
            "the migration:\n  - " + "\n  - ".join(orphans)
        )
        raise RuntimeError(msg)


def upgrade() -> None:
    """Add library_id, backfill, then tighten to NOT NULL."""
    bind = op.get_bind()

    # Step 1: ADD COLUMN NULLABLE so existing rows survive the schema change.
    with op.batch_alter_table("movies") as batch_op:
        batch_op.add_column(
            sa.Column("library_id", sa.String(length=50), nullable=True),
        )
    with op.batch_alter_table("series") as batch_op:
        batch_op.add_column(
            sa.Column("library_id", sa.String(length=50), nullable=True),
        )

    # Step 2: backfill via path matching against the libraries table.
    libraries = _load_libraries(bind)
    movies_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM movies WHERE library_id IS NULL AND deleted_at IS NULL")
    ).scalar_one()
    series_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM series WHERE library_id IS NULL AND deleted_at IS NULL")
    ).scalar_one()
    if (movies_count or series_count) and not libraries:
        msg = (
            f"Cannot backfill library_id: {movies_count} movies and "
            f"{series_count} series exist but no active library is "
            "registered. Create a library that covers their paths "
            "before re-running this migration."
        )
        raise RuntimeError(msg)
    if movies_count:
        _backfill_movies(bind, libraries)
    if series_count:
        _backfill_series(bind, libraries)

    # Step 3: tighten the columns now that every active row has a value
    # and create the supporting index for upcoming per-profile filters.
    with op.batch_alter_table("movies") as batch_op:
        batch_op.alter_column(
            "library_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch_op.create_index("ix_movies_library_id", ["library_id"], unique=False)
    with op.batch_alter_table("series") as batch_op:
        batch_op.alter_column(
            "library_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch_op.create_index("ix_series_library_id", ["library_id"], unique=False)


def downgrade() -> None:
    """Drop library_id from movies and series. Loses scoping data — dev only."""
    with op.batch_alter_table("series") as batch_op:
        batch_op.drop_index("ix_series_library_id")
        batch_op.drop_column("library_id")
    with op.batch_alter_table("movies") as batch_op:
        batch_op.drop_index("ix_movies_library_id")
        batch_op.drop_column("library_id")
