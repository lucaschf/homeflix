"""Tests for the streaming + avatar seed migration (ADR-013 phase 3).

Mirrors ``test_seed_app_settings`` for the phase-3 buckets — the
two migrations share the same helper shape, so the tests run the
private helpers directly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Connection

_SEED_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "2026_05_23_seed_streaming_avatar_settings.py"
)
_spec = importlib.util.spec_from_file_location(
    "_seed_streaming_avatar_migration",
    _SEED_PATH,
)
if _spec is None or _spec.loader is None:
    msg = f"Could not load seed migration at {_SEED_PATH}"
    raise RuntimeError(msg)
_SEED_MODULE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _SEED_MODULE
_spec.loader.exec_module(_SEED_MODULE)


@pytest.fixture
def connection() -> Iterator[Connection]:
    """A throw-away SQLite connection with the ``app_settings`` table."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE app_settings ("
                "key TEXT PRIMARY KEY, "
                "value_json TEXT NOT NULL, "
                "source TEXT NOT NULL, "
                "updated_by_user_id TEXT, "
                "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            )
        )
    with engine.connect() as conn, conn.begin():
        yield conn
    engine.dispose()


@pytest.mark.unit
class TestStreamingEnvHarvest:
    def test_collects_only_set_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FFMPEG_THREADS", "4")
        monkeypatch.delenv("HLS_CACHE_MAX_SIZE_MB", raising=False)

        result = _SEED_MODULE._collect_overrides(_SEED_MODULE._STREAMING_ENV_MAP)

        assert result == {"ffmpeg_threads": "4"}


@pytest.mark.integration
class TestSeedRows:
    def test_seeds_streaming_row_when_env_set(self, connection: Connection) -> None:
        from src.modules.settings.domain.value_objects import (
            SettingKey,
            StreamingConfig,
        )

        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.STREAMING,
            {"ffmpeg_threads": "4", "hls_cache_max_size_mb": "20480"},
            StreamingConfig,
        )

        rows = list(connection.execute(sa.text("SELECT key, value_json, source FROM app_settings")))
        assert len(rows) == 1
        key, value_json, source = rows[0]
        assert key == "streaming"
        assert source == "migration_seed"
        payload = json.loads(value_json)
        assert payload == {
            "ffmpeg_threads": 4,
            "hls_cache_max_size_mb": 20480,
            "hw_accel": "auto",
        }

    def test_seeds_avatar_row_with_partial_overrides(self, connection: Connection) -> None:
        # Only ``size_pixels`` is overridden; the other two fields
        # fall back to ``AvatarConfig`` defaults inside the row.
        from src.modules.settings.domain.value_objects import (
            AvatarConfig,
            SettingKey,
        )

        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.AVATAR,
            {"size_pixels": "512"},
            AvatarConfig,
        )

        rows = list(
            connection.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'avatar'"))
        )
        assert len(rows) == 1
        payload = json.loads(rows[0][0])
        assert payload["size_pixels"] == 512
        # Defaults from the VO survived for the unset fields.
        assert payload["max_size_mb"] == AvatarConfig().max_size_mb
        assert payload["storage_subdir"] == AvatarConfig().storage_subdir

    def test_skips_bucket_when_no_env_set(self, connection: Connection) -> None:
        from src.modules.settings.domain.value_objects import (
            SettingKey,
            StreamingConfig,
        )

        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.STREAMING,
            {},
            StreamingConfig,
        )

        rows = list(connection.execute(sa.text("SELECT COUNT(*) FROM app_settings")))
        assert rows[0][0] == 0
