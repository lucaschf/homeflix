"""Catch up schema with columns and tables never migrated.

Historically the project relied on SQLAlchemy ``create_all`` in dev
mode, which kept the live DB in sync with the models but left the
Alembic history behind. Four tables (``watch_progresses``,
``custom_lists``, ``custom_list_items``, ``watchlist_items``) and
several columns on ``movies`` / ``series`` were never turned into
migrations. This revision brings the migration chain up to parity
with the current model set so a fresh `alembic upgrade head` yields
a fully functional schema.

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6g7h8
Create Date: 2026-04-14 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "c3d4e5f6g7h8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COMMON_TIMESTAMPS = (
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("external_id", sa.String(length=50), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("(CURRENT_TIMESTAMP)"),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("(CURRENT_TIMESTAMP)"),
        nullable=False,
    ),
    sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    """Add missing columns and tables to match current models."""
    # ── movies: credits, classification, trailer, localized metadata ──
    # IMPORTANT: use op.add_column (direct ALTER TABLE) rather than
    # batch_alter_table here. batch_alter_table copies the table in
    # SQLite, which silently breaks the external-content FTS5 link
    # defined in the earlier migration and causes subsequent UPDATEs
    # on movies to raise "database disk image is malformed".
    op.add_column("movies", sa.Column("writers", sa.Text(), nullable=True))
    op.add_column("movies", sa.Column("content_rating", sa.String(length=20), nullable=True))
    op.add_column("movies", sa.Column("trailer_url", sa.String(length=500), nullable=True))
    op.add_column("movies", sa.Column("localized", sa.Text(), nullable=True))

    # ── series: classification, trailer, localized metadata ──
    op.add_column("series", sa.Column("content_rating", sa.String(length=20), nullable=True))
    op.add_column("series", sa.Column("trailer_url", sa.String(length=500), nullable=True))
    op.add_column("series", sa.Column("localized", sa.Text(), nullable=True))

    # ── watch_progresses ─────────────────────────────────────────────
    op.create_table(
        "watch_progresses",
        sa.Column("media_id", sa.String(length=50), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("position_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
        sa.Column("audio_track", sa.Integer(), nullable=True),
        sa.Column("subtitle_track", sa.Integer(), nullable=True),
        sa.Column("last_watched_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        *_COMMON_TIMESTAMPS,
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("watch_progresses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_watch_progresses_deleted_at"), ["deleted_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_watch_progresses_external_id"), ["external_id"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_watch_progresses_media_id"), ["media_id"], unique=True)

    # ── custom_lists ─────────────────────────────────────────────────
    op.create_table(
        "custom_lists",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        *_COMMON_TIMESTAMPS,
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("custom_lists", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_custom_lists_deleted_at"), ["deleted_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_custom_lists_external_id"), ["external_id"], unique=True
        )

    # ── custom_list_items (FK → custom_lists) ────────────────────────
    op.create_table(
        "custom_list_items",
        sa.Column("custom_list_id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.String(length=50), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        *_COMMON_TIMESTAMPS,
        sa.ForeignKeyConstraint(["custom_list_id"], ["custom_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("custom_list_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_custom_list_items_custom_list_id"),
            ["custom_list_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_custom_list_items_deleted_at"), ["deleted_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_custom_list_items_external_id"), ["external_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_custom_list_items_media_id"), ["media_id"], unique=False
        )

    # ── watchlist_items ──────────────────────────────────────────────
    op.create_table(
        "watchlist_items",
        sa.Column("media_id", sa.String(length=50), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        *_COMMON_TIMESTAMPS,
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("watchlist_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_watchlist_items_deleted_at"), ["deleted_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_watchlist_items_external_id"), ["external_id"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_watchlist_items_media_id"), ["media_id"], unique=True)


def downgrade() -> None:
    """Drop the catch-up tables and columns."""
    op.drop_table("watchlist_items")
    op.drop_table("custom_list_items")
    op.drop_table("custom_lists")
    op.drop_table("watch_progresses")

    # NOTE: Proper SQLite downgrade of DROP COLUMN requires
    # batch_alter_table, which in turn would break the FTS5 external
    # content link (see upgrade comment). If you need to downgrade,
    # drop and recreate the FTS5 indexes around these calls. For v1
    # this migration is one-way in practice.
    op.drop_column("series", "localized")
    op.drop_column("series", "trailer_url")
    op.drop_column("series", "content_rating")

    op.drop_column("movies", "localized")
    op.drop_column("movies", "trailer_url")
    op.drop_column("movies", "content_rating")
    op.drop_column("movies", "writers")
