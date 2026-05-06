"""Add preferences table.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6g7"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create preferences table."""
    op.create_table(
        "preferences",
        sa.Column("user_key", sa.String(length=50), nullable=False),
        sa.Column("audio_lang", sa.String(length=10), nullable=False, server_default="pt-BR"),
        sa.Column("subtitle_lang", sa.String(length=10), nullable=False, server_default="pt-BR"),
        sa.Column(
            "subtitle_mode", sa.String(length=20), nullable=False, server_default="foreignOnly"
        ),
        sa.Column("default_quality", sa.String(length=20), nullable=False, server_default="best"),
        sa.Column("speed", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("preferences", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_preferences_deleted_at"), ["deleted_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_preferences_external_id"), ["external_id"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_preferences_user_key"), ["user_key"], unique=True)


def downgrade() -> None:
    """Drop preferences table."""
    op.drop_table("preferences")
