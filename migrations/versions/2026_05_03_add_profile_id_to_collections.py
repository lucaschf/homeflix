"""Add profile_id to collections (custom_lists, watchlist_items).

Per ADR-010, every personalisation row is scoped to a profile. This
migration adds ``profile_id`` to both ``custom_lists`` and
``watchlist_items``, and replaces the legacy ``UNIQUE(media_id)`` on
watchlist with a composite ``UNIQUE(profile_id, media_id)`` so each
profile has its own watchlist row per title.

``custom_list_items`` does not get its own ``profile_id`` column —
items inherit profile scoping through the FK to ``custom_lists``,
which the repository joins through.

Sequence (so existing dev data survives):

1. ADD COLUMN profile_id NULLABLE on both tables.
2. UPDATE legacy rows with the oldest active profile's external_id.
3. ALTER COLUMN profile_id NOT NULL.
4. Drop legacy ``UNIQUE(media_id)`` on watchlist + create composite.

Revision ID: e7f8a9b0c1d2
Revises: f8a9b0c1d2e3
Create Date: 2026-05-03 19:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _resolve_default_profile_external_id(connection: sa.Connection) -> str:
    """Return the prefixed external_id of the oldest active profile.

    Aborts with a clear ``RuntimeError`` if no profile exists so the
    operator runs ``scripts/identity_create_admin.py`` first instead
    of getting a generic NOT NULL violation.
    """
    row = connection.execute(
        sa.text(
            "SELECT external_id "
            "FROM profiles "
            "WHERE deleted_at IS NULL "
            "ORDER BY created_at ASC "
            "LIMIT 1"
        )
    ).first()
    if row is None:
        msg = (
            "Cannot backfill collections.profile_id: no active profile "
            "exists. Run `python scripts/identity_create_admin.py` to create "
            "an admin user and default profile, then re-run this migration."
        )
        raise RuntimeError(msg)
    return row[0]


def upgrade() -> None:
    """Add profile_id to collections + replace legacy unique on watchlist."""
    bind = op.get_bind()

    # Step 1: ADD COLUMN NULLABLE on both tables.
    with op.batch_alter_table("custom_lists") as batch_op:
        batch_op.add_column(
            sa.Column("profile_id", sa.String(length=50), nullable=True),
        )
    with op.batch_alter_table("watchlist_items") as batch_op:
        batch_op.add_column(
            sa.Column("profile_id", sa.String(length=50), nullable=True),
        )

    # Step 2: backfill legacy rows.
    legacy_lists = bind.execute(
        sa.text("SELECT COUNT(*) FROM custom_lists WHERE profile_id IS NULL")
    ).scalar_one()
    legacy_watchlist = bind.execute(
        sa.text("SELECT COUNT(*) FROM watchlist_items WHERE profile_id IS NULL")
    ).scalar_one()
    if legacy_lists or legacy_watchlist:
        default_profile = _resolve_default_profile_external_id(bind)
        if legacy_lists:
            bind.execute(
                sa.text("UPDATE custom_lists SET profile_id = :pid " "WHERE profile_id IS NULL"),
                {"pid": default_profile},
            )
        if legacy_watchlist:
            bind.execute(
                sa.text("UPDATE watchlist_items SET profile_id = :pid " "WHERE profile_id IS NULL"),
                {"pid": default_profile},
            )

    # Step 3: tighten custom_lists.
    with op.batch_alter_table("custom_lists") as batch_op:
        batch_op.alter_column(
            "profile_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch_op.create_index(
            "ix_custom_lists_profile_id",
            ["profile_id"],
            unique=False,
        )

    # Step 4: tighten watchlist_items + replace single-column unique.
    # The legacy schema declared ``media_id`` as ``unique=True, index=True``.
    # Same dialect-dependent shapes as PR 3 — handle defensively.
    op.execute("DROP INDEX IF EXISTS ix_watchlist_items_media_id")
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE watchlist_items " "DROP CONSTRAINT IF EXISTS watchlist_items_media_id_key"
        )
        op.execute(
            "ALTER TABLE watchlist_items " "DROP CONSTRAINT IF EXISTS uq_watchlist_items_media_id"
        )

    with op.batch_alter_table("watchlist_items") as batch_op:
        batch_op.alter_column(
            "profile_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch_op.create_index(
            "ix_watchlist_items_media_id",
            ["media_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_watchlist_items_profile_id",
            ["profile_id"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_watchlist_items_profile_media",
            ["profile_id", "media_id"],
        )


def downgrade() -> None:
    """Reverse the schema change.

    Drops the composite uniques, restores single-column UNIQUE on
    watchlist_items.media_id, and removes the profile_id columns.
    Loses profile scoping data — only safe in dev.
    """
    with op.batch_alter_table("watchlist_items") as batch_op:
        batch_op.drop_constraint(
            "uq_watchlist_items_profile_media",
            type_="unique",
        )
        batch_op.drop_index("ix_watchlist_items_profile_id")
        batch_op.drop_index("ix_watchlist_items_media_id")
        batch_op.create_index(
            "ix_watchlist_items_media_id",
            ["media_id"],
            unique=True,
        )
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("custom_lists") as batch_op:
        batch_op.drop_index("ix_custom_lists_profile_id")
        batch_op.drop_column("profile_id")
