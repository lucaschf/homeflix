"""Add intro-marker columns to episodes and detection-state columns to seasons.

Persists the IntroMarker value object (start/end seconds, source,
optional confidence, detected_at) on each episode, and the
intro-detection job state on each season. New columns are nullable on
``episodes`` (no intro detected/set yet) and seeded with
``NOT_STARTED`` on ``seasons`` so existing rows enter the detection
queue automatically on the next job tick.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-04-29 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add intro columns to ``episodes`` and ``seasons``."""
    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("intro_start_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("intro_end_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("intro_source", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("intro_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("intro_detected_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("seasons", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "intro_detection_state",
                sa.String(length=30),
                nullable=False,
                server_default="NOT_STARTED",
            )
        )
        batch_op.add_column(
            sa.Column(
                "intro_detection_attempted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("intro_detection_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop intro columns from ``seasons`` and ``episodes``."""
    with op.batch_alter_table("seasons", schema=None) as batch_op:
        batch_op.drop_column("intro_detection_error")
        batch_op.drop_column("intro_detection_attempted_at")
        batch_op.drop_column("intro_detection_state")

    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.drop_column("intro_detected_at")
        batch_op.drop_column("intro_confidence")
        batch_op.drop_column("intro_source")
        batch_op.drop_column("intro_end_seconds")
        batch_op.drop_column("intro_start_seconds")
