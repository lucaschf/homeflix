"""Add intro_detection_attempted_episode_count to seasons.

Records how many (non-deleted) episodes a season had the last time the
intro-detection job stamped its state. The job re-arms an
``INSUFFICIENT_EPISODES`` season only once its episode count grows past
this value, so a season that can never satisfy the detector (e.g. a
2-part miniseries) stops being retried on every tick instead of
monopolising the queue. Nullable so existing rows are treated as
"unknown count" (re-eligible exactly once on the next tick, after which
the count is stamped).

Revision ID: 7c2f9a1b3e4d
Revises: c4f7a2b9e1d3
Create Date: 2026-06-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c2f9a1b3e4d"
down_revision: str | Sequence[str] | None = "c4f7a2b9e1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``intro_detection_attempted_episode_count`` to ``seasons``."""
    with op.batch_alter_table("seasons", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "intro_detection_attempted_episode_count",
                sa.Integer(),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Drop ``intro_detection_attempted_episode_count`` from ``seasons``."""
    with op.batch_alter_table("seasons", schema=None) as batch_op:
        batch_op.drop_column("intro_detection_attempted_episode_count")
