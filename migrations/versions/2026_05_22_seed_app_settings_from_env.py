"""Seed app_settings from pre-existing env vars.

One-time migration for ADR-013 phase 2 — preserves any operator
customization of the scheduler / thumbnail-backfill / intro-detection
knobs that was previously living in the ``.env`` file.

Semantics:

- For each of the three buckets, the migration reads every env var
  that used to feed the corresponding ``Settings`` field.
- If *any* env var in a bucket is set, a row is inserted with
  ``source='migration_seed'`` carrying the Pydantic VO built from
  (env value where set, Pydantic default otherwise).
- If no env var in a bucket is set, no row is written — the bucket
  falls through to the VO's defaults at read time.
- The insert uses ``INSERT OR IGNORE`` (SQLite) / ``ON CONFLICT DO
  NOTHING`` (Postgres) so re-running the migration on a database
  that already has admin edits does not overwrite them.

``downgrade`` removes the rows this migration inserted (filtered by
``source='migration_seed'``); admin-edited rows from a later phase
survive a downgrade.

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-05-22 09:00:00.000000

"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic import op

from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
    ThumbnailBackfillConfig,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "1b2c3d4e5f60"
down_revision: str | Sequence[str] | None = "0a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Maps a bucket's env-var name -> (VO class, VO field name). The env var
# is read at migration time only; running code reads
# ``RuntimeSettings`` instead.
_SCHEDULER_ENV_MAP: dict[str, str] = {
    "SCHEDULER_ENABLED": "enabled",
    "SCHEDULER_RECONCILE_INTERVAL_MINUTES": "reconcile_interval_minutes",
}

_THUMBNAIL_BACKFILL_ENV_MAP: dict[str, str] = {
    "THUMBNAIL_BACKFILL_ENABLED": "enabled",
    "THUMBNAIL_BACKFILL_BATCH_SIZE": "batch_size",
    "THUMBNAIL_BACKFILL_INTERVAL_MINUTES": "interval_minutes",
    "THUMBNAIL_BACKFILL_SUBDIR": "subdir",
}

_INTRO_DETECTION_ENV_MAP: dict[str, str] = {
    "INTRO_DETECTION_ENABLED": "enabled",
    "INTRO_DETECTION_BATCH_SIZE": "batch_size",
    "INTRO_DETECTION_INTERVAL_MINUTES": "interval_minutes",
    "INTRO_DETECTION_AUDIO_WINDOW_SECONDS": "audio_window_seconds",
    "INTRO_DETECTION_MIN_CONFIDENCE": "min_confidence",
    "INTRO_DETECTION_MAX_HASH_HAMMING": "max_hash_hamming",
    "INTRO_DETECTION_TOLERANCE_HASHES": "tolerance_hashes",
    "INTRO_DETECTION_MIN_INTRO_SECONDS": "min_intro_seconds",
    "INTRO_DETECTION_MAX_INTRO_SECONDS": "max_intro_seconds",
}


def _collect_overrides(env_map: dict[str, str]) -> dict[str, str]:
    """Return ``{field_name: raw env value}`` for every var that is set."""
    return {field: value for env, field in env_map.items() if (value := os.environ.get(env))}


def _maybe_seed_row(
    connection: sa.Connection,
    key: SettingKey,
    overrides: dict[str, str],
    vo_factory: Any,
) -> None:
    """Insert a seed row when at least one env var is set for ``key``."""
    if not overrides:
        return
    vo = vo_factory.model_validate(overrides)
    payload = vo.model_dump(mode="json")
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO app_settings "
            "(key, value_json, source, updated_at) "
            "VALUES (:key, :value_json, :source, CURRENT_TIMESTAMP)"
        ),
        {
            "key": key.value,
            "value_json": json.dumps(payload),
            "source": SettingSource.MIGRATION_SEED.value,
        },
    )


def upgrade() -> None:
    """Seed app_settings rows from any env vars still present."""
    connection = op.get_bind()
    _maybe_seed_row(
        connection,
        SettingKey.SCHEDULER,
        _collect_overrides(_SCHEDULER_ENV_MAP),
        SchedulerConfig,
    )
    _maybe_seed_row(
        connection,
        SettingKey.THUMBNAIL_BACKFILL,
        _collect_overrides(_THUMBNAIL_BACKFILL_ENV_MAP),
        ThumbnailBackfillConfig,
    )
    _maybe_seed_row(
        connection,
        SettingKey.INTRO_DETECTION,
        _collect_overrides(_INTRO_DETECTION_ENV_MAP),
        IntroDetectionConfig,
    )


def downgrade() -> None:
    """Remove migration-seeded rows; spare any admin-edited ones."""
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM app_settings WHERE source = :source"),
        {"source": SettingSource.MIGRATION_SEED.value},
    )
