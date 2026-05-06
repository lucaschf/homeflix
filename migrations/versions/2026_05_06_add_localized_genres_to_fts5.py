"""Add localized genres to FTS5 search index.

Revision ``b8c9d0e1f2a3`` taught the FTS5 tables how to read
``localized.<lang>.title`` and ``localized.<lang>.synopsis``, but
genres were left behind. The TMDB enrichment populates
``localized = {"pt-BR": {"genres": ["Faroeste", "Ação"], ...}}``
yet the only genre column reachable from search is the root
``movies.genres`` / ``series.genres``, which is always English.

Effect: searching ``"western"`` matched (root column hit) while
``"faroeste"`` matched nothing — the Portuguese genre lived in
the JSON blob but was never indexed.

This migration adds a ``localized_genres`` column to both FTS5
tables and populates it via nested ``json_each`` — the outer
loop iterates languages in ``localized``, the inner loop iterates
each language's ``genres`` array, and ``GROUP_CONCAT`` flattens
them into a single tokenizable string.

FTS5 virtual tables don't support ``ALTER TABLE ADD COLUMN``, so
the only path is DROP + CREATE + repopulate (same shape as the
two prior FTS5 migrations).

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-06 09:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reusable SQL fragments. ``localized`` is shaped
# ``{"pt-BR": {"title": "...", "genres": ["Faroeste", ...], ...}, ...}``
# so titles/synopses live one level deep but genres are a nested
# array. Outer ``json_each`` walks the language map; for genres
# we cross-join an inner ``json_each`` over the array. ``json_each``
# raises on NULL, hence the ``COALESCE`` defaults to ``'{}'`` /
# ``'[]'``.

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
        "title, original_title, synopsis, genres, "
        '"cast", directors, localized_titles, localized_synopses, '
        "localized_genres"
    )


def _series_columns() -> str:
    return (
        "title, original_title, synopsis, genres, "
        "localized_titles, localized_synopses, localized_genres"
    )


def _movie_values(alias: str) -> str:
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


def _series_values(alias: str) -> str:
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.genres, ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_GENRES.format(alias=alias).strip()}
    """


def upgrade() -> None:
    """Recreate FTS5 tables and triggers with localized_genres."""
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
    """Restore the FTS5 schema without the localized_genres column."""
    op.execute("DROP TRIGGER IF EXISTS movies_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TABLE IF EXISTS movies_fts")

    op.execute("DROP TRIGGER IF EXISTS series_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")
    op.execute("DROP TABLE IF EXISTS series_fts")

    # Reuse the column/value shape from b8c9d0e1f2a3 (titles +
    # synopses, no genres) so the downgraded state matches the
    # previous head bit-for-bit.

    movie_columns = (
        "title, original_title, synopsis, genres, "
        '"cast", directors, localized_titles, localized_synopses'
    )
    series_columns = (
        "title, original_title, synopsis, genres, " "localized_titles, localized_synopses"
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
            {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()}
        """

    def series_values(alias: str) -> str:
        return f"""
            COALESCE({alias}.title, ''),
            COALESCE({alias}.original_title, ''),
            COALESCE({alias}.synopsis, ''),
            COALESCE({alias}.genres, ''),
            {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
            {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()}
        """

    op.execute(
        """
        CREATE VIRTUAL TABLE movies_fts USING fts5(
            title, original_title, synopsis, genres, "cast", directors,
            localized_titles, localized_synopses,
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
            localized_titles, localized_synopses,
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
