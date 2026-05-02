"""Create catalog_requests table.

The Catalog Requests bounded context tracks user-initiated
"please add this title" intents and optional "notify me when it
arrives" subscriptions. Single-user platform, so a single row
per ``(tmdb_id, media_type)`` is enough — no per-user fanout.

The Collection Detail page reads request status alongside the
local catalog when stitching the FilmRow CTAs (Solicitar inclusão
vs. Pedido registrado vs. Avisar quando chegar), so the
``(tmdb_id, media_type)`` lookup needs an index.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-02 12:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``catalog_requests`` table."""
    op.create_table(
        "catalog_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("collection_tmdb_id", sa.Integer(), nullable=True),
        sa.Column(
            "notify_on_arrival",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_catalog_requests_external_id",
        "catalog_requests",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_catalog_requests_tmdb_id",
        "catalog_requests",
        ["tmdb_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_requests_collection_tmdb_id",
        "catalog_requests",
        ["collection_tmdb_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_requests_fulfilled_at",
        "catalog_requests",
        ["fulfilled_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_requests_deleted_at",
        "catalog_requests",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_requests_tmdb_id_media_type",
        "catalog_requests",
        ["tmdb_id", "media_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ``catalog_requests`` table."""
    op.drop_index("ix_catalog_requests_tmdb_id_media_type", table_name="catalog_requests")
    op.drop_index("ix_catalog_requests_deleted_at", table_name="catalog_requests")
    op.drop_index("ix_catalog_requests_fulfilled_at", table_name="catalog_requests")
    op.drop_index(
        "ix_catalog_requests_collection_tmdb_id",
        table_name="catalog_requests",
    )
    op.drop_index("ix_catalog_requests_tmdb_id", table_name="catalog_requests")
    op.drop_index("ix_catalog_requests_external_id", table_name="catalog_requests")
    op.drop_table("catalog_requests")
