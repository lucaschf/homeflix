"""Add parental unlock and lockout state to access_tokens.

Four columns, per session and so per device (ADR-035, Amendment 7 D4):

- ``parental_failed_attempts`` and ``parental_lockouts`` (the ladder
  step): INTEGER NOT NULL with server default 0. FastAPI Users' login
  inserts only ``token`` and ``user_id``, so the database must fill them;
  the default also back-fills every existing session with 0.
- ``parental_locked_until`` and ``parental_unlock_until``: nullable
  INTEGER epoch seconds (UTC), NULL on every existing session.

Written by hand with ``op.add_column``, like ``ed6c3864ea50`` and
``7737e1954c0c``. The batch form ``migrations/env.py`` renders for SQLite
rebuilds ``access_tokens`` by copy-and-rename when a column carries a
server default. No foreign key points at ``access_tokens``, so the
rebuild would not lose rows, but ``ALTER TABLE ... ADD COLUMN`` keeps the
table and needs no copy. The downgrade uses the native ``DROP COLUMN``.
``tests/infrastructure/migrations/test_identity_parental_migrations.py``
runs this revision with foreign keys on over the previous schema.

Revision ID: fe6dc087a1a4
Revises: 7737e1954c0c
Create Date: 2026-09-14 16:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "fe6dc087a1a4"
down_revision: str | Sequence[str] | None = "7737e1954c0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COUNTERS = ("parental_failed_attempts", "parental_lockouts")
_TIMES = ("parental_locked_until", "parental_unlock_until")


def upgrade() -> None:
    """Add the lockout counters (NOT NULL DEFAULT 0) and the two epoch times."""
    for name in _COUNTERS:
        op.add_column(
            "access_tokens",
            sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    for name in _TIMES:
        op.add_column("access_tokens", sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop the four parental columns."""
    for name in reversed(_COUNTERS + _TIMES):
        op.drop_column("access_tokens", name)
