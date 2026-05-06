"""Cover remaining searchable fields in FTS5.

Audit after PR #188 (``e3f4a5b6c7d8``) found several text columns
that are populated by the catalog/enrichment paths but were never
projected into the FTS5 inverted index:

- ``movies.tagline`` (added 2026-05-01) — promotional one-liner,
  obvious search target ("Just when you thought it was safe...").
- ``movies.localized.<lang>.tagline`` — TMDB enrichment fills the
  pt-BR tagline; same one-liner, in Portuguese.
- ``movies.writers`` — populated alongside ``cast`` / ``directors``
  but only the latter two were indexed.
- ``movies.collection_name`` — franchise label ("Alien Collection",
  "MCU"); searching by franchise should resolve to its members.
- ``series.cast`` (added 2026-05-01) — actor names. Equivalent
  field on ``movies`` is indexed; series fell out by oversight.

This migration adds those columns to ``movies_fts`` /
``series_fts`` and recreates the six sync triggers in lock-step.
FTS5 still has no ``ALTER TABLE ADD COLUMN``, so DROP + CREATE +
repopulate is the only path.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-05-06 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f4a5b6c7d8e9"
down_revision: str | Sequence[str] | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reusable SQL fragments. The localized titles/synopses/genres
# patterns are unchanged from prior migrations; localized_taglines
# follows the same shape as titles/synopses since tagline is a
# scalar field one level deep in the JSON.

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

_MOVIES_LOCALIZED_TAGLINES = """
COALESCE(
    (SELECT GROUP_CONCAT(json_extract(value, '$.tagline'), ' ')
     FROM json_each(COALESCE({alias}.localized, '{{}}'))
     WHERE json_extract(value, '$.tagline') IS NOT NULL),
    ''
)
"""

_MOVIES_LOCALIZED_GENRES = """
COALESCE(
    (SELECT GROUP_CONCAT(g.value, ' ')
     FROM json_each(COALESCE({alias}.localized, '{{}}')) AS lang,
          json_each(COALESCE(json_extract(lang.value, '$.genres'), '[]')) AS g),
    ''
)
"""


def _movie_columns() -> str:
    return (
        "title, original_title, synopsis, tagline, genres, "
        '"cast", directors, writers, collection_name, '
        "localized_titles, localized_synopses, localized_taglines, "
        "localized_genres"
    )


def _series_columns() -> str:
    return (
        "title, original_title, synopsis, genres, "
        '"cast", '
        "localized_titles, localized_synopses, localized_genres"
    )


def _movie_values(alias: str) -> str:
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.tagline, ''),
        COALESCE({alias}.genres, ''),
        COALESCE({alias}."cast", ''),
        COALESCE({alias}.directors, ''),
        COALESCE({alias}.writers, ''),
        COALESCE({alias}.collection_name, ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_TAGLINES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_GENRES.format(alias=alias).strip()}
    """


def _series_values(alias: str) -> str:
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.genres, ''),
        COALESCE({alias}."cast", ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_GENRES.format(alias=alias).strip()}
    """


def upgrade() -> None:
    """Recreate FTS5 tables and triggers covering the missing fields."""
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
            tagline,
            genres,
            "cast",
            directors,
            writers,
            collection_name,
            localized_titles,
            localized_synopses,
            localized_taglines,
            localized_genres,
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
            "cast",
            localized_titles,
            localized_synopses,
            localized_genres,
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
    """Restore the FTS5 schema from revision e3f4a5b6c7d8."""
    op.execute("DROP TRIGGER IF EXISTS movies_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TABLE IF EXISTS movies_fts")

    op.execute("DROP TRIGGER IF EXISTS series_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")
    op.execute("DROP TABLE IF EXISTS series_fts")

    movie_columns = (
        "title, original_title, synopsis, genres, "
        '"cast", directors, localized_titles, localized_synopses, '
        "localized_genres"
    )
    series_columns = (
        "title, original_title, synopsis, genres, "
        "localized_titles, localized_synopses, localized_genres"
    )

    def movie_values(alias: str) -> str:
        return f"""
            COALESCE({alias}.title, ''),
            COALESCE({alias}.original_title, ''),
            COALESCE({alias}.synopsis, ''),
            COALESCE({alias}.genres, ''),
            COALESCE({alias}."cast", ''),
            COALESCE({alias}.directors, ''),
            {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
            {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()},
            {_MOVIES_LOCALIZED_GENRES.format(alias=alias).strip()}
        """

    def series_values(alias: str) -> str:
        return f"""
            COALESCE({alias}.title, ''),
            COALESCE({alias}.original_title, ''),
            COALESCE({alias}.synopsis, ''),
            COALESCE({alias}.genres, ''),
            {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
            {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()},
            {_MOVIES_LOCALIZED_GENRES.format(alias=alias).strip()}
        """

    op.execute(
        """
        CREATE VIRTUAL TABLE movies_fts USING fts5(
            title, original_title, synopsis, genres, "cast", directors,
            localized_titles, localized_synopses, localized_genres,
            content='movies',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    op.execute(
        f"""
        INSERT INTO movies_fts(rowid, {movie_columns})
        SELECT id, {movie_values("movies")}
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
            INSERT INTO movies_fts(rowid, {movie_columns})
            VALUES (NEW.id, {movie_values("NEW")});
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER movies_fts_update AFTER UPDATE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, {movie_columns})
            VALUES ('delete', OLD.id, {movie_values("OLD")});
            INSERT INTO movies_fts(rowid, {movie_columns})
            SELECT NEW.id, {movie_values("NEW")}
            WHERE NEW.deleted_at IS NULL;
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER movies_fts_delete AFTER DELETE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, {movie_columns})
            VALUES ('delete', OLD.id, {movie_values("OLD")});
        END
        """
    )

    op.execute(
        """
        CREATE VIRTUAL TABLE series_fts USING fts5(
            title, original_title, synopsis, genres,
            localized_titles, localized_synopses, localized_genres,
            content='series',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    op.execute(
        f"""
        INSERT INTO series_fts(rowid, {series_columns})
        SELECT id, {series_values("series")}
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
            INSERT INTO series_fts(rowid, {series_columns})
            VALUES (NEW.id, {series_values("NEW")});
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER series_fts_update AFTER UPDATE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, {series_columns})
            VALUES ('delete', OLD.id, {series_values("OLD")});
            INSERT INTO series_fts(rowid, {series_columns})
            SELECT NEW.id, {series_values("NEW")}
            WHERE NEW.deleted_at IS NULL;
        END
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER series_fts_delete AFTER DELETE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, {series_columns})
            VALUES ('delete', OLD.id, {series_values("OLD")});
        END
        """
    )
