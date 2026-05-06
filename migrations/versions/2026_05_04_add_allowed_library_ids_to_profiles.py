"""Add allowed_library_ids ACL list to profiles.

Per ADR-010, every profile carries the set of libraries it may
see in the catalog (the ACL the upcoming PR 6c filter will
consume). Stored as a JSON-encoded TEXT list — reads are always
"the whole list per profile" and library cardinality is small,
so a join table would buy nothing.

Backfill semantics: pre-existing profiles inherit the snapshot of
every active library at migration time. That preserves their
current "see everything" experience without silently auto-granting
access to libraries that get added later — once the ACL exists,
new libraries become explicit-grant-only.

Sequence:

1. ADD COLUMN allowed_library_ids TEXT NULLABLE.
2. UPDATE all rows with a JSON list of every active library
   external_id (or ``[]`` when no libraries exist yet).
3. ALTER COLUMN allowed_library_ids NOT NULL with server_default
   ``"[]"`` so future rows default-deny.

Revision ID: c1d2e3f4a5b6
Revises: b09c1d2e3f4a
Create Date: 2026-05-04 11:00:00.000000

"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b09c1d2e3f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column, backfill from current libraries, then tighten."""
    bind = op.get_bind()

    # Step 1: add the column nullable so existing rows survive.
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(sa.Column("allowed_library_ids", sa.Text(), nullable=True))

    # Step 2: backfill. Every existing profile inherits the snapshot
    # of currently-active library external_ids; downstream the catalog
    # filter will read this column verbatim, so the snapshot preserves
    # the pre-ACL "see everything" behavior. New libraries added after
    # this migration require an explicit grant via the profile API.
    libraries = bind.execute(
        sa.text("SELECT external_id FROM libraries WHERE deleted_at IS NULL")
    ).fetchall()
    snapshot = json.dumps([row[0] for row in libraries])
    bind.execute(
        sa.text(
            "UPDATE profiles SET allowed_library_ids = :snapshot "
            "WHERE allowed_library_ids IS NULL"
        ),
        {"snapshot": snapshot},
    )

    # Step 3: tighten. server_default ``"[]"`` so any future INSERT
    # that forgets to populate the column lands on the safe (deny-all)
    # value rather than NULL.
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.alter_column(
            "allowed_library_ids",
            existing_type=sa.Text(),
            nullable=False,
            server_default="[]",
        )


def downgrade() -> None:
    """Drop the column. Loses ACL configuration — dev only."""
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_column("allowed_library_ids")
