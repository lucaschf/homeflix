"""Replace user_key with profile_id on preferences (singleton-per-profile).

Per ADR-010, every personalisation row is scoped to a profile. The
``preferences`` table predates identity and used a placeholder
``user_key`` column whose only value was ``"default"``. This
migration introduces ``profile_id`` (the prefixed external ID — no
FK because cross-BC references travel as strings, not UUIDs) and
drops ``user_key`` once the legacy rows have been backfilled.

Sequence (so existing dev data survives):

1. ADD COLUMN profile_id NULLABLE — schema accepts NULL for the
   handful of legacy rows already present.
2. UPDATE the legacy rows with the first profile's external_id —
   requires that ``scripts/identity_create_admin.py`` was run before
   the upgrade so at least one profile exists. Migration aborts with
   a clear message if not.
3. DROP UNIQUE(user_key) and DROP COLUMN user_key.
4. ALTER COLUMN profile_id NOT NULL + UNIQUE.

Revision ID: f8a9b0c1d2e3
Revises: d6e7f8a9b0c1
Create Date: 2026-05-03 19:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
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
            "Cannot backfill preferences.profile_id: no active profile "
            "exists. Run `python scripts/identity_create_admin.py` to create "
            "an admin user and default profile, then re-run this migration."
        )
        raise RuntimeError(msg)
    return row[0]


def upgrade() -> None:
    """Add profile_id, backfill, drop legacy user_key, tighten the column."""
    bind = op.get_bind()

    # Step 1: ADD COLUMN NULLABLE so existing rows survive the schema change.
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column("profile_id", sa.String(length=50), nullable=True),
        )

    # Step 2: backfill legacy rows with the oldest active profile.
    legacy_rows = bind.execute(
        sa.text("SELECT COUNT(*) FROM preferences WHERE profile_id IS NULL")
    ).scalar_one()
    if legacy_rows:
        default_profile = _resolve_default_profile_external_id(bind)
        bind.execute(
            sa.text("UPDATE preferences SET profile_id = :pid WHERE profile_id IS NULL"),
            {"pid": default_profile},
        )

    # Step 3: drop the legacy user_key column. The unique index travels
    # with the column on SQLite (table-rebuild via batch_alter_table)
    # and on Postgres an explicit DROP INDEX IF EXISTS keeps the path
    # idempotent against partially-applied prior runs.
    op.execute("DROP INDEX IF EXISTS ix_preferences_user_key")
    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE preferences DROP CONSTRAINT IF EXISTS preferences_user_key_key")
        op.execute("ALTER TABLE preferences DROP CONSTRAINT IF EXISTS uq_preferences_user_key")

    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("user_key")
        batch_op.alter_column(
            "profile_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch_op.create_index(
            "ix_preferences_profile_id",
            ["profile_id"],
            unique=True,
        )


def downgrade() -> None:
    """Reverse the schema change.

    Restores ``user_key`` (server_default ``'default'``) and drops
    ``profile_id``. Note: this loses per-profile scoping data — only
    safe in dev.
    """
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "user_key",
                sa.String(length=50),
                nullable=False,
                server_default="default",
            ),
        )
        batch_op.drop_index("ix_preferences_profile_id")
        batch_op.drop_column("profile_id")
        batch_op.create_index(
            "ix_preferences_user_key",
            ["user_key"],
            unique=True,
        )
