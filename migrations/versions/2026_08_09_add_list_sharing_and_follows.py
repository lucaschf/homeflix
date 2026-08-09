"""Add custom-list sharing (share_token) + list_follows table.

Two changes back the share/follow feature:

- ``custom_lists.share_token`` — an opaque, nullable secret. NULL means
  the list is not shared; a value means it is. A partial unique index
  (live rows only) guarantees one live token per value and lets a
  follower resolve a list by token.
- ``list_follows`` — one row per ``(follower_profile_id, list_id)``
  follow, mirroring ``catalog_subscriptions``. A partial unique index
  (live rows only) keeps a repeat follow idempotent without blocking a
  re-follow after an unfollow soft-deletes the row.

Revision ID: 3c7f2a9d1b46
Revises: 5d0b7e1c9a3f
Create Date: 2026-08-09 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "3c7f2a9d1b46"
down_revision: str | Sequence[str] | None = "5d0b7e1c9a3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = text("deleted_at IS NULL")
_SHARED = text("share_token IS NOT NULL AND deleted_at IS NULL")


def upgrade() -> None:
    """Add the share_token column and the list_follows table."""
    op.add_column(
        "custom_lists",
        sa.Column("share_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_custom_lists_share_token",
        "custom_lists",
        ["share_token"],
        unique=False,
    )
    # One live list per token value (excludes NULL / soft-deleted rows).
    op.create_index(
        "uq_custom_lists_share_token",
        "custom_lists",
        ["share_token"],
        unique=True,
        sqlite_where=_SHARED,
        postgresql_where=_SHARED,
    )

    op.create_table(
        "list_follows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("follower_profile_id", sa.String(length=50), nullable=False),
        sa.Column("list_id", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_list_follows_external_id",
        "list_follows",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_list_follows_follower_profile_id",
        "list_follows",
        ["follower_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_list_follows_list_id",
        "list_follows",
        ["list_id"],
        unique=False,
    )
    op.create_index(
        "ix_list_follows_deleted_at",
        "list_follows",
        ["deleted_at"],
        unique=False,
    )
    # One live follow per (follower, list) — partial so a soft-deleted
    # unfollow doesn't block re-following.
    op.create_index(
        "uq_list_follows_follower_list",
        "list_follows",
        ["follower_profile_id", "list_id"],
        unique=True,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )


def downgrade() -> None:
    """Drop the list_follows table and the share_token column."""
    op.drop_index("uq_list_follows_follower_list", table_name="list_follows")
    op.drop_index("ix_list_follows_deleted_at", table_name="list_follows")
    op.drop_index("ix_list_follows_list_id", table_name="list_follows")
    op.drop_index("ix_list_follows_follower_profile_id", table_name="list_follows")
    op.drop_index("ix_list_follows_external_id", table_name="list_follows")
    op.drop_table("list_follows")

    op.drop_index("uq_custom_lists_share_token", table_name="custom_lists")
    op.drop_index("ix_custom_lists_share_token", table_name="custom_lists")
    op.drop_column("custom_lists", "share_token")
