"""Add normalized minimum age and rating system to movies and series.

Both columns are nullable and nothing reads them yet (ADR-035): this
revision only gives the catalog somewhere to keep the comparable form of
a certification. The data migration derives an age for every row that
already carries a label, so the feature has coverage the day the filter
is switched on instead of waiting on a re-enrichment of the whole
library.

The back-fill touches live rows only (``deleted_at IS NULL``), matching
the sibling back-fill in ``2026_05_04_add_library_id_to_movies_and_series``.
A soft-deleted title needs no age — it is invisible to every query — and
updating one is actively harmful: the FTS5 external-content triggers on
``movies`` / ``series`` fire on *any* UPDATE and emit a ``'delete'`` for
the old row, but a soft-deleted row was already removed from the index,
so the second delete drives the index's ``nDoc``/``avgdl`` below the
truth. Those two are the inputs to ``bm25()``, so an unscoped back-fill
silently skews search ranking across the whole catalog — and on a small
database drives the counter negative, aborting the migration with
"database disk image is malformed".

The label-to-age table is **copied here on purpose** instead of being
imported from ``shared_kernel.content_policy``. A migration is frozen
history: if it imported the live table, a later change to it — say
reading MPA ``PG`` by release era — would silently change what this
revision does when replayed, and two databases with identical migration
histories would end up with different data. The duplication is guarded
by ``test_minimum_age_migration_snapshot``, which fails when the live
table drifts from this snapshot so the drift is a decision (update the
snapshot, or write a new data migration) rather than a surprise.

Revision ID: a7e4c91d20b8
Revises: f1a6d0c72e93
Create Date: 2026-09-12 14:20:00.000000

"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "a7e4c91d20b8"
down_revision: str | Sequence[str] | None = "f1a6d0c72e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen snapshot of shared_kernel.content_policy.certification_scale as
# of this revision. See the module docstring for why it is copied.
SCALE_SNAPSHOT: dict[str, tuple[str, int]] = {
    # Brazilian Classificação Indicativa
    "L": ("br_dejus", 0),
    "AL": ("br_dejus", 0),
    "LIVRE": ("br_dejus", 0),
    "A10": ("br_dejus", 10),
    "A12": ("br_dejus", 12),
    "A14": ("br_dejus", 14),
    "A16": ("br_dejus", 16),
    "A18": ("br_dejus", 18),
    # MPA film ratings
    "G": ("us_mpa", 0),
    "PG": ("us_mpa", 13),
    "PG-13": ("us_mpa", 13),
    "PG13": ("us_mpa", 13),
    "R": ("us_mpa", 17),
    "NC-17": ("us_mpa", 18),
    "NC17": ("us_mpa", 18),
    # US television parental guidelines
    "TV-Y": ("us_tv", 0),
    "TV-Y7": ("us_tv", 7),
    "TV-Y7-FV": ("us_tv", 7),
    "TV-G": ("us_tv", 0),
    "TV-PG": ("us_tv", 10),
    "TV-14": ("us_tv", 14),
    "TV-MA": ("us_tv", 17),
}

UNRATED_SNAPSHOT: frozenset[str] = frozenset(
    {"NR", "UR", "N/A", "NA", "NOT RATED", "UNRATED", "NONE", "-"}
)

NUMERIC_SNAPSHOT = re.compile(r"^(\d{1,2})\+?$")

AGE_CEILING = 21


def _derive(label: str) -> tuple[str, int] | None:
    """Snapshot of ``classify`` for a label of unknown jurisdiction.

    The existing rows do not record which country their label came from,
    so this takes the countryless path: bare numerals read as the generic
    numeric scale rather than being attributed to Brazil. The age is the
    same either way; only the recorded system differs, and claiming less
    is the honest option for data being back-filled.
    """
    token = " ".join(label.split()).upper()
    if not token or token in UNRATED_SNAPSHOT:
        return None

    known = SCALE_SNAPSHOT.get(token)
    if known is not None:
        return known

    match = NUMERIC_SNAPSHOT.match(token)
    if match is not None:
        return "numeric", min(int(match.group(1)), AGE_CEILING)

    return None


def upgrade() -> None:
    """Add the columns, index them with library_id, and back-fill ages."""
    for table in ("movies", "series"):
        op.add_column(table, sa.Column("minimum_age", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("rating_system", sa.String(20), nullable=True))
        op.create_index(
            f"ix_{table}_library_minimum_age",
            table,
            ["library_id", "minimum_age"],
        )

    connection = op.get_bind()

    for table in ("movies", "series"):
        rows = connection.execute(
            sa.text(
                # ``table`` is one of two literals from the loop above, never input.
                f"SELECT DISTINCT content_rating FROM {table} "
                "WHERE content_rating IS NOT NULL AND TRIM(content_rating) <> '' "
                "AND deleted_at IS NULL"
            )
        ).fetchall()

        for (label,) in rows:
            derived = _derive(label)
            if derived is None:
                # Explicitly unrated or unrecognized: leave both columns
                # NULL. The domain reads a missing age as adult, so these
                # titles stay out of every limited profile — which is the
                # intended fail-closed behavior, not an omission.
                continue

            system, age = derived
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET minimum_age = :age, rating_system = :system "
                    "WHERE content_rating = :label AND deleted_at IS NULL"
                ),
                {"age": age, "system": system, "label": label},
            )


def downgrade() -> None:
    """Drop the index and both columns."""
    for table in ("movies", "series"):
        op.drop_index(f"ix_{table}_library_minimum_age", table_name=table)
        op.drop_column(table, "rating_system")
        op.drop_column(table, "minimum_age")
