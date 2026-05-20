"""Create notifications table.

Backs the new ``notifications`` bounded context — Layer B of the
catalog-request rollout. Every cross-BC handler that wants to
ping a specific user writes a row here, and the header bell
renders it. Per-recipient rows (no broadcast / fan-out table)
keep the read-side a straight ``WHERE recipient_user_id = ?``.
Kind-specific extras (deep-link target, tmdb anchor, etc.) live
in the ``payload`` JSON so adding a new kind later doesn't need
a migration.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-05-20 13:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notifications`` table."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_notifications_external_id",
        "notifications",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_notifications_recipient_user_id",
        "notifications",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_read_at",
        "notifications",
        ["read_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_deleted_at",
        "notifications",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ``notifications`` table."""
    op.drop_index("ix_notifications_deleted_at", table_name="notifications")
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_index("ix_notifications_external_id", table_name="notifications")
    op.drop_table("notifications")
