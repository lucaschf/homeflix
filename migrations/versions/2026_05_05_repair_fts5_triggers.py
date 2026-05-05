"""Repair FTS5 triggers + reindex movies / series after schema changes.

Migration ``b09c1d2e3f4a`` (PR #175 — add ``library_id`` to movies
and series) used Alembic's ``batch_alter_table`` to add the new
column. On SQLite that operation does a table-rebuild dance
(create new, copy rows, drop old, rename) and silently
cascade-drops every trigger that referenced the old table — in
this case the six FTS5 sync triggers (``insert`` / ``update`` /
``delete`` for both ``movies_fts`` and ``series_fts``).

Without those triggers, every scan after PR #175 added catalog
rows that never made it into the FTS5 inverted index. The user
hit this as ""search returns nothing"" once their catalog grew
beyond the rows that had been indexed BEFORE the batch_alter ran.

This migration:

1. Drops the existing FTS5 virtual tables + any leftover
   triggers (defensive ``IF EXISTS``).
2. Recreates ``movies_fts`` / ``series_fts`` with the same
   schema as ``b8c9d0e1f2a3`` (root columns +
   ``localized_titles`` + ``localized_synopses``).
3. Re-populates from ``movies`` / ``series`` (active rows only,
   ``deleted_at IS NULL``).
4. Recreates the six sync triggers so future scans stay
   indexed.

Future-proofing: any future ``batch_alter_table`` on
``movies`` or ``series`` must be paired with a re-run of this
recreation logic in the same migration. See the comment in
``b09c1d2e3f4a``'s upgrade for the lesson.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-05 09:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d2e3f4a5b6c7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reusable SQL fragments — kept identical to the originals in
# ``2026_04_25_add_localized_to_fts5_search.py`` so the recreated
# state matches what callers expect bit-for-bit.

_MOVIES_LOCALIZED_TITLES = """
COALESCE(
    (SELECT GROUP_CONCAT(json_extract(value, '$.title'), ' ')
     FROM json_each(COALESCE({alias}.localized, '{{}}'))
     WHERE json_extract(value, '$.title') IS NOT NULL),
    ''
)
"""

_MOVIES_LOCALIZED_SYNOPSES = """
COALESCE(
    (SELECT GROUP_CONCAT(json_extract(value, '$.synopsis'), ' ')
     FROM json_each(COALESCE({alias}.localized, '{{}}'))
     WHERE json_extract(value, '$.synopsis') IS NOT NULL),
    ''
)
"""


def _movie_columns() -> str:
    return (
        "title, original_title, synopsis, genres, "
        '"cast", directors, localized_titles, localized_synopses'
    )


def _series_columns() -> str:
    return "title, original_title, synopsis, genres, localized_titles, localized_synopses"


def _movie_values(alias: str) -> str:
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.genres, ''),
        COALESCE({alias}."cast", ''),
        COALESCE({alias}.directors, ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()}
    """


def _series_values(alias: str) -> str:
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.genres, ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()}
    """


def upgrade() -> None:
    """Drop, recreate and repopulate the FTS5 tables + their triggers."""
    # ── Drop everything that needs to be recreated ────────────────
    op.execute("DROP TRIGGER IF EXISTS movies_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TABLE IF EXISTS movies_fts")

    op.execute("DROP TRIGGER IF EXISTS series_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")
    op.execute("DROP TABLE IF EXISTS series_fts")

    # ── Movies FTS5 ──────────────────────────────────────────────
    op.execute(
        """
        CREATE VIRTUAL TABLE movies_fts USING fts5(
            title,
            original_title,
            synopsis,
            genres,
            "cast",
            directors,
            localized_titles,
            localized_synopses,
            content='movies',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    op.execute(
        f"""
        INSERT INTO movies_fts(rowid, {_movie_columns()})
        SELECT id, {_movie_values("movies")}
        FROM movies
        WHERE deleted_at IS NULL
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER movies_fts_insert
        AFTER INSERT ON movies
        WHEN NEW.deleted_at IS NULL
        BEGIN
            INSERT INTO movies_fts(rowid, {_movie_columns()})
            VALUES (NEW.id, {_movie_values("NEW")});
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER movies_fts_update AFTER UPDATE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, {_movie_columns()})
            VALUES ('delete', OLD.id, {_movie_values("OLD")});
            INSERT INTO movies_fts(rowid, {_movie_columns()})
            SELECT NEW.id, {_movie_values("NEW")}
            WHERE NEW.deleted_at IS NULL;
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER movies_fts_delete AFTER DELETE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, {_movie_columns()})
            VALUES ('delete', OLD.id, {_movie_values("OLD")});
        END
        """
    )

    # ── Series FTS5 ──────────────────────────────────────────────
    op.execute(
        """
        CREATE VIRTUAL TABLE series_fts USING fts5(
            title,
            original_title,
            synopsis,
            genres,
            localized_titles,
            localized_synopses,
            content='series',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    op.execute(
        f"""
        INSERT INTO series_fts(rowid, {_series_columns()})
        SELECT id, {_series_values("series")}
        FROM series
        WHERE deleted_at IS NULL
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER series_fts_insert
        AFTER INSERT ON series
        WHEN NEW.deleted_at IS NULL
        BEGIN
            INSERT INTO series_fts(rowid, {_series_columns()})
            VALUES (NEW.id, {_series_values("NEW")});
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER series_fts_update AFTER UPDATE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, {_series_columns()})
            VALUES ('delete', OLD.id, {_series_values("OLD")});
            INSERT INTO series_fts(rowid, {_series_columns()})
            SELECT NEW.id, {_series_values("NEW")}
            WHERE NEW.deleted_at IS NULL;
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER series_fts_delete AFTER DELETE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, {_series_columns()})
            VALUES ('delete', OLD.id, {_series_values("OLD")});
        END
        """
    )


def downgrade() -> None:
    """No-op.

    The "broken" pre-state (no triggers, stale FTS index) isn't
    something we want to deliberately restore. Downgrade is a
    one-way trapdoor here.
    """
