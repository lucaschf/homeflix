"""Add scrub_preview_path columns to movies and episodes.

Backfilled lazily by ThumbnailBackfillJob, so existing rows stay
``NULL`` until that job processes them. New rows default to ``NULL``
because the upload/scan pipeline does not block on sprite generation.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add scrub_preview_path columns to movies and episodes."""
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scrub_preview_path", sa.String(length=2000), nullable=True))
    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scrub_preview_path", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    """Drop scrub_preview_path columns from movies and episodes."""
    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.drop_column("scrub_preview_path")
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_column("scrub_preview_path")
