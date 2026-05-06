"""Create users, profiles, and access_tokens for the identity BC.

Introduces the identity bounded context tables per ADR-010 (User/Profile
boundary, UUID interno + prefixed external_id) and ADR-011 (server-side
sessions via cookie + DatabaseStrategy).

Schema notes:
- UUID primary keys via ``fastapi_users_db_sqlalchemy.GUID`` (CHAR(36)
  on SQLite, UUID on Postgres).
- ``external_id`` columns on ``users`` and ``profiles`` for the prefixed
  domain ID exposed to clients. ``access_tokens`` has no external_id —
  the token is a secret, never exposed.
- ``profiles.user_id`` ``ON DELETE CASCADE``: deleting an account
  removes its profiles.
- ``access_tokens.user_id`` ``ON DELETE CASCADE``: deleting an account
  invalidates its sessions.
- ``access_tokens.current_profile_id`` ``ON DELETE SET NULL``: deleting
  a profile clears it from any session that had it active, prompting
  the user to pick a new one rather than failing the session.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-03 17:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``users``, ``profiles``, and ``access_tokens`` tables."""
    op.create_table(
        "users",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="member",
        ),
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
        "ix_users_external_id",
        "users",
        ["external_id"],
        unique=True,
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index(
        "ix_users_deleted_at",
        "users",
        ["deleted_at"],
        unique=False,
    )

    op.create_table(
        "profiles",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_kids",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        "ix_profiles_external_id",
        "profiles",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_profiles_user_id",
        "profiles",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_profiles_deleted_at",
        "profiles",
        ["deleted_at"],
        unique=False,
    )

    op.create_table(
        "access_tokens",
        sa.Column("token", sa.String(length=43), primary_key=True),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "current_profile_id",
            GUID(),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_access_tokens_user_id",
        "access_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the identity tables in dependency order (FKs first)."""
    op.drop_index("ix_access_tokens_user_id", table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_index("ix_profiles_deleted_at", table_name="profiles")
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_index("ix_profiles_external_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_table("users")
