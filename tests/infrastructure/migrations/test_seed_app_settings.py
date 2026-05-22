"""Tests for the app_settings seed migration (ADR-013 phase 2).

Exercises ``_collect_overrides`` (env-var harvest) and
``_maybe_seed_row`` (idempotent insert into ``app_settings``). Drives
the live SQLAlchemy connection against an in-memory SQLite engine so
the JSON serialization and ``INSERT OR IGNORE`` semantics are
verified end-to-end without booting Alembic.
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

# The migration file lives outside the importable ``src`` tree and its
# date-prefixed filename is not a valid Python identifier — load it by
# path so the tests can reach the private helpers.
_SEED_PATH = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "2026_05_22_seed_app_settings_from_env.py"
)
_spec = importlib.util.spec_from_file_location(
    "_seed_app_settings_migration",
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
class TestCollectOverrides:
    def test_empty_when_no_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for env in _SEED_MODULE._INTRO_DETECTION_ENV_MAP:
            monkeypatch.delenv(env, raising=False)

        result = _SEED_MODULE._collect_overrides(_SEED_MODULE._INTRO_DETECTION_ENV_MAP)

        assert result == {}

    def test_returns_only_fields_whose_env_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INTRO_DETECTION_ENABLED", "true")
        monkeypatch.setenv("INTRO_DETECTION_BATCH_SIZE", "3")
        monkeypatch.delenv("INTRO_DETECTION_AUDIO_WINDOW_SECONDS", raising=False)

        result = _SEED_MODULE._collect_overrides(_SEED_MODULE._INTRO_DETECTION_ENV_MAP)

        assert result == {"enabled": "true", "batch_size": "3"}


@pytest.mark.integration
class TestMaybeSeedRow:
    def test_writes_row_when_overrides_present(self, connection: Connection) -> None:
        from src.modules.settings.domain.value_objects import (
            SchedulerConfig,
            SettingKey,
        )

        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.SCHEDULER,
            {"enabled": "false", "reconcile_interval_minutes": "42"},
            SchedulerConfig,
        )

        rows = list(connection.execute(sa.text("SELECT key, value_json, source FROM app_settings")))
        assert len(rows) == 1
        key, value_json, source = rows[0]
        assert key == "scheduler"
        assert source == "migration_seed"
        assert json.loads(value_json) == {
            "enabled": False,
            "reconcile_interval_minutes": 42,
        }

    def test_skips_when_no_overrides(self, connection: Connection) -> None:
        from src.modules.settings.domain.value_objects import (
            SchedulerConfig,
            SettingKey,
        )

        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.SCHEDULER,
            {},
            SchedulerConfig,
        )

        rows = list(connection.execute(sa.text("SELECT COUNT(*) FROM app_settings")))
        assert rows[0][0] == 0

    def test_idempotent_does_not_overwrite_existing_row(self, connection: Connection) -> None:
        from src.modules.settings.domain.value_objects import (
            SchedulerConfig,
            SettingKey,
        )

        # Seed once with one set of values...
        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.SCHEDULER,
            {"reconcile_interval_minutes": "10"},
            SchedulerConfig,
        )
        # ...then re-run with different values — the row must not be
        # overwritten (INSERT OR IGNORE semantics).
        _SEED_MODULE._maybe_seed_row(
            connection,
            SettingKey.SCHEDULER,
            {"reconcile_interval_minutes": "99"},
            SchedulerConfig,
        )

        rows = list(connection.execute(sa.text("SELECT value_json FROM app_settings")))
        assert len(rows) == 1
        assert json.loads(rows[0][0])["reconcile_interval_minutes"] == 10
