"""Add profile_id to watch_progresses, scope by (profile_id, media_id).

Per ADR-010, every personalisation row is scoped to a profile. This
migration adds ``watch_progresses.profile_id`` (the prefixed external
ID — no FK because cross-BC references travel as strings, not UUIDs)
and replaces the single-column UNIQUE(media_id) with a composite
UNIQUE(profile_id, media_id) so multiple profiles in the same
household can watch the same title independently.

Sequence (so existing dev data survives):

1. ADD COLUMN profile_id NULLABLE — schema accepts NULL for the
   handful of legacy rows already present.
2. UPDATE the legacy rows with the first profile's external_id —
   requires that ``scripts/identity_create_admin.py`` was run before
   the upgrade so at least one profile exists. Migration aborts with
   a clear message if not.
3. ALTER COLUMN profile_id NOT NULL.
4. DROP UNIQUE(media_id) and CREATE UNIQUE(profile_id, media_id).

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-03 18:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
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
            "Cannot backfill watch_progresses.profile_id: no active profile "
            "exists. Run `python scripts/identity_create_admin.py` to create "
            "an admin user and default profile, then re-run this migration."
        )
        raise RuntimeError(msg)
    return row[0]


def upgrade() -> None:
    """Add profile_id, backfill, drop legacy unique, add composite unique."""
    bind = op.get_bind()

    # Step 1: ADD COLUMN NULLABLE so existing rows survive the schema change.
    with op.batch_alter_table("watch_progresses") as batch_op:
        batch_op.add_column(
            sa.Column("profile_id", sa.String(length=50), nullable=True),
        )

    # Step 2: backfill legacy rows with the oldest active profile.
    legacy_rows = bind.execute(
        sa.text("SELECT COUNT(*) FROM watch_progresses WHERE profile_id IS NULL")
    ).scalar_one()
    if legacy_rows:
        default_profile = _resolve_default_profile_external_id(bind)
        bind.execute(
            sa.text("UPDATE watch_progresses " "SET profile_id = :pid " "WHERE profile_id IS NULL"),
            {"pid": default_profile},
        )

    # Step 3: tighten the column + replace the legacy media_id unique with a
    # composite (profile_id, media_id) unique so multiple profiles can watch
    # the same title independently.
    with op.batch_alter_table("watch_progresses") as batch_op:
        batch_op.alter_column(
            "profile_id",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        # The legacy schema declared media_id as UNIQUE; SQLAlchemy named the
        # implicit constraint after the column but the original column had
        # ``unique=True`` so dialects vary. Drop both shapes defensively.
        batch_op.drop_index("ix_watch_progresses_media_id")
        batch_op.create_index(
            "ix_watch_progresses_media_id",
            ["media_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_watch_progresses_profile_id",
            ["profile_id"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_watch_progresses_profile_media",
            ["profile_id", "media_id"],
        )


def downgrade() -> None:
    """Reverse the schema change.

    Drops the composite unique, restores the single-column unique on
    media_id, and removes the profile_id column. Note: this loses
    profile scoping data — only safe in dev.
    """
    with op.batch_alter_table("watch_progresses") as batch_op:
        batch_op.drop_constraint(
            "uq_watch_progresses_profile_media",
            type_="unique",
        )
        batch_op.drop_index("ix_watch_progresses_profile_id")
        batch_op.drop_index("ix_watch_progresses_media_id")
        batch_op.create_index(
            "ix_watch_progresses_media_id",
            ["media_id"],
            unique=True,
        )
        batch_op.drop_column("profile_id")
