"""Seed app_settings rows for streaming + avatar buckets.

Phase-3 sibling of ``2026_05_22_seed_app_settings_from_env``: same
shape, same semantics (read any pre-existing env var, write one row
per bucket as ``source='migration_seed'``, skip when nothing is set,
INSERT OR IGNORE so re-runs and admin edits are preserved).

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-05-23 09:00:00.000000

"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic import op

from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    SettingKey,
    SettingSource,
    StreamingConfig,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "2c3d4e5f6071"
down_revision: str | Sequence[str] | None = "1b2c3d4e5f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STREAMING_ENV_MAP: dict[str, str] = {
    "FFMPEG_THREADS": "ffmpeg_threads",
    "HLS_CACHE_MAX_SIZE_MB": "hls_cache_max_size_mb",
}

_AVATAR_ENV_MAP: dict[str, str] = {
    "AVATAR_STORAGE_SUBDIR": "storage_subdir",
    "AVATAR_MAX_SIZE_MB": "max_size_mb",
    "AVATAR_SIZE_PIXELS": "size_pixels",
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
    """Seed streaming + avatar rows from any env vars still present."""
    connection = op.get_bind()
    _maybe_seed_row(
        connection,
        SettingKey.STREAMING,
        _collect_overrides(_STREAMING_ENV_MAP),
        StreamingConfig,
    )
    _maybe_seed_row(
        connection,
        SettingKey.AVATAR,
        _collect_overrides(_AVATAR_ENV_MAP),
        AvatarConfig,
    )


def downgrade() -> None:
    """Remove the rows this migration would have written.

    Filtered by ``key IN ('streaming', 'avatar') AND source =
    'migration_seed'`` so admin-edited rows survive — same caveat as
    the phase-2 migration's downgrade.
    """
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM app_settings " "WHERE source = :source AND key IN ('streaming', 'avatar')"
        ),
        {"source": SettingSource.MIGRATION_SEED.value},
    )
