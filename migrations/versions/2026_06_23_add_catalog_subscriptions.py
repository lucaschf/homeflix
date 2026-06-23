"""Create catalog_subscriptions table + backfill from catalog_requests.

ADR-022 splits "the title is in the queue" (``catalog_requests``)
from "who wants to be notified" (this table). Each row is one user's
opt-in to a queued title's arrival ping — the per-user fanout layer
the single-owner model lacked.

``(request_id, user_id)`` is unique among live rows so a repeat
"Avisar quando chegar" stays idempotent. The backfill turns every
existing request that had ``notify_on_arrival = TRUE`` and a known
``requester_user_id`` into one subscription, so nobody who was
already waiting loses their notification when the model flips.

Revision ID: 7a1c93b5e2d8
Revises: aa11bb22cc33
Create Date: 2026-06-23 18:00:00.000000

"""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "7a1c93b5e2d8"
down_revision: str | Sequence[str] | None = "aa11bb22cc33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = text("deleted_at IS NULL")

# Base62 id generation, inlined so the migration stays independent of
# the app's domain code (avoids schema-vs-code drift). Mirrors
# ``ExternalId.generate()``: ``sub_`` + 12 base62 chars.
_BASE62 = string.ascii_letters + string.digits


def _gen_subscription_id() -> str:
    return "sub_" + "".join(secrets.choice(_BASE62) for _ in range(12))


def upgrade() -> None:
    """Create ``catalog_subscriptions`` and backfill existing opt-ins."""
    op.create_table(
        "catalog_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("request_id", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=False),
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
        "ix_catalog_subscriptions_external_id",
        "catalog_subscriptions",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_catalog_subscriptions_request_id",
        "catalog_subscriptions",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_subscriptions_user_id",
        "catalog_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_subscriptions_deleted_at",
        "catalog_subscriptions",
        ["deleted_at"],
        unique=False,
    )
    # One live subscription per (request, user) — partial so a
    # soft-deleted unsubscribe doesn't block re-subscribing.
    op.create_index(
        "uq_catalog_subscriptions_request_user",
        "catalog_subscriptions",
        ["request_id", "user_id"],
        unique=True,
        sqlite_where=_LIVE,
        postgresql_where=_LIVE,
    )

    _backfill_from_requests()


def _backfill_from_requests() -> None:
    """Seed one subscription per already-opted-in request."""
    connection = op.get_bind()
    rows = connection.execute(
        text(
            "SELECT external_id, requester_user_id "
            "FROM catalog_requests "
            "WHERE notify_on_arrival = :flag "
            "AND requester_user_id IS NOT NULL "
            "AND deleted_at IS NULL"
        ),
        {"flag": True},
    ).fetchall()

    for request_external_id, requester_user_id in rows:
        connection.execute(
            text(
                "INSERT INTO catalog_subscriptions "
                "(external_id, request_id, user_id) "
                "VALUES (:eid, :rid, :uid)"
            ),
            {
                "eid": _gen_subscription_id(),
                "rid": request_external_id,
                "uid": requester_user_id,
            },
        )


def downgrade() -> None:
    """Drop the ``catalog_subscriptions`` table."""
    op.drop_index(
        "uq_catalog_subscriptions_request_user",
        table_name="catalog_subscriptions",
    )
    op.drop_index(
        "ix_catalog_subscriptions_deleted_at",
        table_name="catalog_subscriptions",
    )
    op.drop_index(
        "ix_catalog_subscriptions_user_id",
        table_name="catalog_subscriptions",
    )
    op.drop_index(
        "ix_catalog_subscriptions_request_id",
        table_name="catalog_subscriptions",
    )
    op.drop_index(
        "ix_catalog_subscriptions_external_id",
        table_name="catalog_subscriptions",
    )
    op.drop_table("catalog_subscriptions")
