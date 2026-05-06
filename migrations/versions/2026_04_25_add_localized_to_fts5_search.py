"""Add localized titles/synopses to FTS5 search index.

The original FTS5 schema (rev ``a1b2c3d4e5f6``) only indexed root
columns: ``title``, ``original_title``, ``synopsis``, plus a few
others. Movies and series carry a ``localized`` JSON column with
per-language overrides shaped like
``{"pt-BR": {"title": "...", "synopsis": "..."}, "en": {...}}``,
but none of that text was reachable from search queries — a movie
whose original title is "Total Recall" and pt-BR title is
"Vingador do Futuro" could not be found by searching "vingador".

Add ``localized_titles`` and ``localized_synopses`` columns to both
FTS5 tables, populated via SQLite's ``json_each`` + ``json_extract``
in the sync triggers so any number of languages flows through
without schema changes.

FTS5 virtual tables don't support ``ALTER TABLE ADD COLUMN``, so
the only path is DROP + CREATE + repopulate. Triggers are recreated
along with the tables since the column list changed.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-25 03:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reusable SQL fragments. Defined once so the column list and the
# JSON traversal stay consistent across the populate query and the
# three triggers (insert / update / delete) per FTS table — keeps
# this migration auditable instead of buried in copy-paste.

# ``json_each`` raises on NULL input, hence the COALESCE to ``'{}'``
# on the source column. ``WHERE json_extract(...) IS NOT NULL`` keeps
# stray separators out of the concatenated payload when a language
# override only sets one of the two fields.

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
    """Comma-separated list of FTS5 movies columns (excluding rowid)."""
    return (
        "title, original_title, synopsis, genres, "
        '"cast", directors, localized_titles, localized_synopses'
    )


def _series_columns() -> str:
    """Comma-separated list of FTS5 series columns (excluding rowid)."""
    return "title, original_title, synopsis, genres, localized_titles, localized_synopses"


def _movie_values(alias: str) -> str:
    """VALUES tuple matching ``_movie_columns()`` against a row alias."""
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
    """VALUES tuple matching ``_series_columns()`` against a row alias."""
    return f"""
        COALESCE({alias}.title, ''),
        COALESCE({alias}.original_title, ''),
        COALESCE({alias}.synopsis, ''),
        COALESCE({alias}.genres, ''),
        {_MOVIES_LOCALIZED_TITLES.format(alias=alias).strip()},
        {_MOVIES_LOCALIZED_SYNOPSES.format(alias=alias).strip()}
    """


def upgrade() -> None:
    """Recreate FTS5 tables and triggers with localized fields."""
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
    """Restore the FTS5 schema without localized columns."""
    op.execute("DROP TRIGGER IF EXISTS movies_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TABLE IF EXISTS movies_fts")

    op.execute("DROP TRIGGER IF EXISTS series_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")
    op.execute("DROP TABLE IF EXISTS series_fts")

    op.execute(
        """
        CREATE VIRTUAL TABLE movies_fts USING fts5(
            title, original_title, synopsis, genres, "cast", directors,
            content='movies',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """
    )

    op.execute(
        """
        INSERT INTO movies_fts(rowid, title, original_title, synopsis, genres, "cast", directors)
        SELECT id,
               COALESCE(title, ''),
               COALESCE(original_title, ''),
               COALESCE(synopsis, ''),
               COALESCE(genres, ''),
               COALESCE("cast", ''),
               COALESCE(directors, '')
        FROM movies
        WHERE deleted_at IS NULL
    """
    )

    op.execute(
        """
        CREATE TRIGGER movies_fts_insert
        AFTER INSERT ON movies
        WHEN NEW.deleted_at IS NULL
        BEGIN
            INSERT INTO movies_fts(rowid, title, original_title, synopsis, genres,
                                   "cast", directors)
            VALUES (NEW.id,
                    COALESCE(NEW.title, ''),
                    COALESCE(NEW.original_title, ''),
                    COALESCE(NEW.synopsis, ''),
                    COALESCE(NEW.genres, ''),
                    COALESCE(NEW."cast", ''),
                    COALESCE(NEW.directors, ''));
        END
    """
    )

    op.execute(
        """
        CREATE TRIGGER movies_fts_update AFTER UPDATE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, title, original_title,
                                   synopsis, genres, "cast", directors)
            VALUES ('delete',
                    OLD.id,
                    COALESCE(OLD.title, ''),
                    COALESCE(OLD.original_title, ''),
                    COALESCE(OLD.synopsis, ''),
                    COALESCE(OLD.genres, ''),
                    COALESCE(OLD."cast", ''),
                    COALESCE(OLD.directors, ''));
            INSERT INTO movies_fts(rowid, title, original_title,
                                   synopsis, genres, "cast", directors)
            SELECT NEW.id,
                   COALESCE(NEW.title, ''),
                   COALESCE(NEW.original_title, ''),
                   COALESCE(NEW.synopsis, ''),
                   COALESCE(NEW.genres, ''),
                   COALESCE(NEW."cast", ''),
                   COALESCE(NEW.directors, '')
            WHERE NEW.deleted_at IS NULL;
        END
    """
    )

    op.execute(
        """
        CREATE TRIGGER movies_fts_delete AFTER DELETE ON movies BEGIN
            INSERT INTO movies_fts(movies_fts, rowid, title, original_title,
                                   synopsis, genres, "cast", directors)
            VALUES ('delete',
                    OLD.id,
                    COALESCE(OLD.title, ''),
                    COALESCE(OLD.original_title, ''),
                    COALESCE(OLD.synopsis, ''),
                    COALESCE(OLD.genres, ''),
                    COALESCE(OLD."cast", ''),
                    COALESCE(OLD.directors, ''));
        END
    """
    )

    op.execute(
        """
        CREATE VIRTUAL TABLE series_fts USING fts5(
            title, original_title, synopsis, genres,
            content='series',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """
    )

    op.execute(
        """
        INSERT INTO series_fts(rowid, title, original_title, synopsis, genres)
        SELECT id,
               COALESCE(title, ''),
               COALESCE(original_title, ''),
               COALESCE(synopsis, ''),
               COALESCE(genres, '')
        FROM series
        WHERE deleted_at IS NULL
    """
    )

    op.execute(
        """
        CREATE TRIGGER series_fts_insert
        AFTER INSERT ON series
        WHEN NEW.deleted_at IS NULL
        BEGIN
            INSERT INTO series_fts(rowid, title, original_title, synopsis, genres)
            VALUES (NEW.id,
                    COALESCE(NEW.title, ''),
                    COALESCE(NEW.original_title, ''),
                    COALESCE(NEW.synopsis, ''),
                    COALESCE(NEW.genres, ''));
        END
    """
    )

    op.execute(
        """
        CREATE TRIGGER series_fts_update AFTER UPDATE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, title, original_title,
                                   synopsis, genres)
            VALUES ('delete',
                    OLD.id,
                    COALESCE(OLD.title, ''),
                    COALESCE(OLD.original_title, ''),
                    COALESCE(OLD.synopsis, ''),
                    COALESCE(OLD.genres, ''));
            INSERT INTO series_fts(rowid, title, original_title, synopsis, genres)
            SELECT NEW.id,
                   COALESCE(NEW.title, ''),
                   COALESCE(NEW.original_title, ''),
                   COALESCE(NEW.synopsis, ''),
                   COALESCE(NEW.genres, '')
            WHERE NEW.deleted_at IS NULL;
        END
    """
    )

    op.execute(
        """
        CREATE TRIGGER series_fts_delete AFTER DELETE ON series BEGIN
            INSERT INTO series_fts(series_fts, rowid, title, original_title,
                                   synopsis, genres)
            VALUES ('delete',
                    OLD.id,
                    COALESCE(OLD.title, ''),
                    COALESCE(OLD.original_title, ''),
                    COALESCE(OLD.synopsis, ''),
                    COALESCE(OLD.genres, ''));
        END
    """
    )
