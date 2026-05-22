"""Unit tests for :class:`RuntimeSettings` (snapshot + TTL behavior)."""

from collections.abc import Sequence
from typing import Self

import pytest

from src.modules.settings.application.unit_of_work import SettingsUnitOfWork
from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.repositories import SettingRepository
from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
)
from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


class _FakeRepo(SettingRepository):
    def __init__(self, rows: list[Setting]) -> None:
        self.rows = rows
        self.list_calls = 0

    async def list_all(self) -> Sequence[Setting]:
        self.list_calls += 1
        return list(self.rows)

    async def find_by_key(self, key: SettingKey) -> Setting | None:
        return next((r for r in self.rows if r.id is key), None)

    async def upsert(self, setting: Setting) -> Setting:
        self.rows = [r for r in self.rows if r.id is not setting.id]
        self.rows.append(setting)
        return setting


class _FakeUoW(SettingsUnitOfWork):
    def __init__(self, repo: _FakeRepo) -> None:
        self.settings = repo

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakeUoWFactory:
    def __init__(self, repo: _FakeRepo) -> None:
        self.repo = repo
        self.calls = 0

    def __call__(self) -> _FakeUoW:
        self.calls += 1
        return _FakeUoW(self.repo)


@pytest.fixture
def admin_intro_row() -> Setting:
    return Setting(
        id=SettingKey.INTRO_DETECTION,
        value=IntroDetectionConfig(enabled=True, min_confidence=0.9),
        source=SettingSource.ADMIN,
        updated_by_user_id="usr_admin",
    )


class TestRuntimeSettingsDefaults:
    async def test_returns_defaults_when_table_empty(self) -> None:
        repo = _FakeRepo(rows=[])
        rs = RuntimeSettings(_FakeUoWFactory(repo))

        scheduler = await rs.scheduler()
        intro = await rs.intro_detection()

        assert scheduler == SchedulerConfig()
        assert intro == IntroDetectionConfig()


class TestRuntimeSettingsOverrides:
    async def test_db_row_overrides_default(self, admin_intro_row: Setting) -> None:
        repo = _FakeRepo(rows=[admin_intro_row])
        rs = RuntimeSettings(_FakeUoWFactory(repo))

        intro = await rs.intro_detection()

        assert intro.enabled is True
        assert intro.min_confidence == 0.9

    async def test_unmigrated_keys_still_fall_back_to_default(
        self, admin_intro_row: Setting
    ) -> None:
        repo = _FakeRepo(rows=[admin_intro_row])
        rs = RuntimeSettings(_FakeUoWFactory(repo))

        scheduler = await rs.scheduler()

        assert scheduler == SchedulerConfig()


class TestRuntimeSettingsCaching:
    async def test_ttl_caches_until_expiry(self, admin_intro_row: Setting) -> None:
        repo = _FakeRepo(rows=[admin_intro_row])
        rs = RuntimeSettings(_FakeUoWFactory(repo), cache_ttl_seconds=300)

        for _ in range(5):
            await rs.intro_detection()

        assert repo.list_calls == 1

    async def test_invalidate_forces_next_read_to_refresh(self, admin_intro_row: Setting) -> None:
        repo = _FakeRepo(rows=[admin_intro_row])
        rs = RuntimeSettings(_FakeUoWFactory(repo), cache_ttl_seconds=300)

        await rs.intro_detection()
        assert repo.list_calls == 1

        await rs.invalidate()
        await rs.intro_detection()

        assert repo.list_calls == 2

    async def test_refresh_picks_up_newly_inserted_row(self) -> None:
        repo = _FakeRepo(rows=[])
        rs = RuntimeSettings(_FakeUoWFactory(repo), cache_ttl_seconds=300)

        assert (await rs.scheduler()).enabled is True  # default

        new_row = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=False, reconcile_interval_minutes=99),
            source=SettingSource.ADMIN,
        )
        await repo.upsert(new_row)
        await rs.refresh()

        scheduler = await rs.scheduler()
        assert scheduler.enabled is False
        assert scheduler.reconcile_interval_minutes == 99
