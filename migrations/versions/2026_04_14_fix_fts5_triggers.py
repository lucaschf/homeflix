"""Fix FTS5 sync triggers to use external-content-safe commands.

The original triggers in revision ``a1b2c3d4e5f6`` used plain
``DELETE FROM movies_fts WHERE rowid = OLD.id`` to remove rows from
the FTS5 virtual table. That syntax is *not* valid for FTS5 tables
declared with ``content='...'`` (external content mode) — the
correct call is the special ``'delete'`` command that also tells
FTS5 the full prior value of each indexed column:

    INSERT INTO movies_fts(movies_fts, rowid, title, ...)
        VALUES('delete', OLD.id, OLD.title, ...);

Some SQLite builds (notably the ones shipping with Python on
Windows) now reject the old syntax with
``database disk image is malformed`` when the offending trigger
fires — for example, every UPDATE on ``movies`` during metadata
enrichment. This revision drops the broken triggers and recreates
them with the correct external-content commands.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-14 23:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace the broken FTS5 sync triggers with correct ones."""
    # ── Movies ───────────────────────────────────────────────────────
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")

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

    # ── Series ───────────────────────────────────────────────────────
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")

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
            INSERT INTO series_fts(rowid, title, original_title,
                                   synopsis, genres)
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

    # Rebuild the FTS5 indexes in case any stale deletes left orphaned
    # rows that would confuse future queries.
    op.execute("INSERT INTO movies_fts(movies_fts) VALUES('rebuild')")
    op.execute("INSERT INTO series_fts(series_fts) VALUES('rebuild')")


def downgrade() -> None:
    """Restore the original (broken) triggers."""
    op.execute("DROP TRIGGER IF EXISTS movies_fts_update")
    op.execute("DROP TRIGGER IF EXISTS movies_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS series_fts_update")
    op.execute("DROP TRIGGER IF EXISTS series_fts_delete")

    op.execute(
        """
        CREATE TRIGGER movies_fts_update AFTER UPDATE ON movies BEGIN
            DELETE FROM movies_fts WHERE rowid = OLD.id;
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
            DELETE FROM movies_fts WHERE rowid = OLD.id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER series_fts_update AFTER UPDATE ON series BEGIN
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
        CREATE TRIGGER series_fts_delete AFTER DELETE ON series BEGIN
            DELETE FROM series_fts WHERE rowid = OLD.id;
        END
        """
    )
