"""Add description column to custom_lists.

Lets users attach an optional free-text description to a custom list
(shown in the list-detail header). Nullable so existing lists are
unaffected.

Revision ID: d8e2f4a6c1b9
Revises: 7c2f9a1b3e4d
Create Date: 2026-06-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e2f4a6c1b9"
down_revision: str | Sequence[str] | None = "7c2f9a1b3e4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``description`` to ``custom_lists``.

    Plain ``add_column`` (not batch) so SQLite uses a native
    ``ALTER TABLE ADD COLUMN`` instead of a table-recreate — the latter
    trips the ``custom_list_items`` FK when the table holds data.
    """
    op.add_column("custom_lists", sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Drop ``description`` from ``custom_lists`` (native, no recreate)."""
    op.drop_column("custom_lists", "description")
