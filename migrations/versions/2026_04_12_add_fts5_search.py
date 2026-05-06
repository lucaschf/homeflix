"""Add FTS5 virtual tables for full-text search.

Revision ID: a1b2c3d4e5f6
Revises: 435d635e4b18
Create Date: 2026-04-12 12:00:00.000000

Creates FTS5 virtual tables indexing the searchable text columns
of movies and series (title, original_title, synopsis, genres,
cast/directors for movies). Triggers keep the FTS index in sync
on INSERT, UPDATE, and DELETE — no application-layer bookkeeping
needed.

The `content` and `content_rowid` options link each FTS5 virtual
table to its corresponding content table so the index doesn't
duplicate the raw text — FTS5 reads it from the original row at
query time (external-content mode). This halves the storage
overhead compared to a standalone FTS5 table.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "435d635e4b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create FTS5 virtual tables and sync triggers."""
    # ── Movies FTS5 ──────────────────────────────────────────────
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS movies_fts USING fts5(
            title,
            original_title,
            synopsis,
            genres,
            "cast",
            directors,
            content='movies',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """
    )

    # Populate from existing rows
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

    # Triggers to keep FTS in sync
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS movies_fts_insert
        AFTER INSERT ON movies
        WHEN NEW.deleted_at IS NULL
        BEGIN
            INSERT INTO movies_fts(rowid, title, original_title, synopsis, genres, "cast", directors)
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
        CREATE TRIGGER IF NOT EXISTS movies_fts_update
        AFTER UPDATE ON movies
        BEGIN
            DELETE FROM movies_fts WHERE rowid = OLD.id;
            INSERT INTO movies_fts(rowid, title, original_title, synopsis, genres, "cast", directors)
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
        CREATE TRIGGER IF NOT EXISTS movies_fts_delete
        AFTER DELETE ON movies
        BEGIN
            DELETE FROM movies_fts WHERE rowid = OLD.id;
        END
    """
    )

    # ── Series FTS5 ──────────────────────────────────────────────
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS series_fts USING fts5(
            title,
            original_title,
            synopsis,
            genres,
            content='series',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """
    )

    # Populate from existing rows
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

    # Triggers
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS series_fts_insert
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
        CREATE TRIGGER IF NOT EXISTS series_fts_update
        AFTER UPDATE ON series
        BEGIN
            DELETE FROM series_fts WHERE rowid = OLD.id;
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
        CREATE TRIGGER IF NOT EXISTS series_fts_delete
        AFTER DELETE ON series
        BEGIN
            DELETE FROM series_fts WHERE rowid = OLD.id;
        END
    """
    )


def downgrade() -> None:
    """Drop FTS5 tables and triggers."""
    # Triggers are dropped automatically when the parent table's
    # triggers are removed, but explicit DROP is safer.
    op.execute("DROP TRIGGER IF EXISTS movies_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TABLE IF EXISTS movies_fts")

    op.execute("DROP TRIGGER IF EXISTS series_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")
    op.execute("DROP TABLE IF EXISTS series_fts")
