"""Create app_settings table.

Backs ADR-013 — operational tunables move out of ``.env`` into the
database, grouped one row per Value Object (intro detection,
scheduler, thumbnail backfill, streaming, avatar). The primary key is
the semantic ``key`` string (an enum value mirrored by
``SettingKey``); the row carries the entire serialized VO in
``value_json`` plus provenance (``source``) and audit fields.

This table deliberately diverges from the ``Base`` convention used by
domain aggregates: no surrogate integer id, no ``external_id``, no
soft-delete column. The semantic key *is* the identity, and rows are
upserted or absent — never archived. Precedent: ``BaseSecret`` follows
the same shape.

Note: ADR-013 lists the schema as ``key, value_json, source,
updated_at, updated_by_user_id``. ``created_at`` is added here so the
mapper does not have to fabricate the ``DomainEntity.created_at``
field on hydration; the deviation is intentional and documented in
the PR.

Revision ID: 0a1b2c3d4e5f
Revises: f1a2b3c4d5e6
Create Date: 2026-05-21 10:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0a1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``app_settings`` table."""
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=50), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=50), nullable=True),
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
    )


def downgrade() -> None:
    """Drop the ``app_settings`` table."""
    op.drop_table("app_settings")
