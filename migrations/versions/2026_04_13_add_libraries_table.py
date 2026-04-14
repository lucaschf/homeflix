"""Add libraries table.

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create libraries table."""
    op.create_table(
        "libraries",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("library_type", sa.String(length=20), nullable=False),
        sa.Column("paths", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("metadata_providers", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("scan_schedule", sa.String(length=100), nullable=True),
        sa.Column("settings", sa.Text(), nullable=False, server_default="{}"),
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
    with op.batch_alter_table("libraries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_libraries_deleted_at"), ["deleted_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_libraries_external_id"), ["external_id"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_libraries_library_type"), ["library_type"], unique=False
        )


def downgrade() -> None:
    """Drop libraries table."""
    op.drop_table("libraries")
