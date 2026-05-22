"""Unit tests for :class:`UpdateSettingUseCase`."""

from collections.abc import Sequence
from typing import Self
from unittest.mock import AsyncMock

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.application.dtos import UpdateSettingInput
from src.modules.settings.application.unit_of_work import SettingsUnitOfWork
from src.modules.settings.application.use_cases import UpdateSettingUseCase
from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.repositories import SettingRepository
from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
)


class _FakeRepo(SettingRepository):
    def __init__(self, rows: list[Setting]) -> None:
        self.rows = rows
        self.upserts: list[Setting] = []

    async def list_all(self) -> Sequence[Setting]:
        return list(self.rows)

    async def find_by_key(self, key: SettingKey) -> Setting | None:
        return next((r for r in self.rows if r.id is key), None)

    async def upsert(self, setting: Setting) -> Setting:
        self.upserts.append(setting)
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

    def __call__(self) -> _FakeUoW:
        return _FakeUoW(self.repo)


@pytest.fixture
def runtime_settings_mock() -> AsyncMock:
    """Mock with an awaitable ``invalidate`` so the use case can call it."""
    return AsyncMock()


@pytest.mark.unit
class TestUpdateSetting:
    async def test_persists_admin_row_with_acting_admin_id(
        self,
        runtime_settings_mock: AsyncMock,
    ) -> None:
        repo = _FakeRepo(rows=[])
        use_case = UpdateSettingUseCase(_FakeUoWFactory(repo), runtime_settings_mock)

        detail = await use_case.execute(
            UpdateSettingInput(
                key=SettingKey.SCHEDULER.value,
                value=SchedulerConfig(enabled=False, reconcile_interval_minutes=10).model_dump(
                    mode="json"
                ),
                acting_admin_id="usr_admin",
            ),
        )

        assert len(repo.upserts) == 1
        persisted = repo.upserts[0]
        assert persisted.id is SettingKey.SCHEDULER
        assert persisted.source is SettingSource.ADMIN
        assert persisted.updated_by_user_id == "usr_admin"
        assert isinstance(persisted.value, SchedulerConfig)
        assert persisted.value.enabled is False
        assert persisted.value.reconcile_interval_minutes == 10
        assert detail.source == "admin"

    async def test_invalidates_runtime_settings_cache_after_upsert(
        self,
        runtime_settings_mock: AsyncMock,
    ) -> None:
        use_case = UpdateSettingUseCase(
            _FakeUoWFactory(_FakeRepo(rows=[])),
            runtime_settings_mock,
        )

        await use_case.execute(
            UpdateSettingInput(
                key=SettingKey.INTRO_DETECTION.value,
                value=IntroDetectionConfig(min_confidence=0.85).model_dump(mode="json"),
                acting_admin_id="usr_admin",
            ),
        )

        runtime_settings_mock.invalidate.assert_awaited_once()

    async def test_overwrites_existing_row_for_same_key(
        self,
        runtime_settings_mock: AsyncMock,
    ) -> None:
        existing = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=True, reconcile_interval_minutes=5),
            source=SettingSource.MIGRATION_SEED,
        )
        repo = _FakeRepo(rows=[existing])
        use_case = UpdateSettingUseCase(_FakeUoWFactory(repo), runtime_settings_mock)

        await use_case.execute(
            UpdateSettingInput(
                key=SettingKey.SCHEDULER.value,
                value=SchedulerConfig(enabled=False, reconcile_interval_minutes=30).model_dump(
                    mode="json"
                ),
                acting_admin_id="usr_admin",
            ),
        )

        scheduler_rows = [r for r in repo.rows if r.id is SettingKey.SCHEDULER]
        assert len(scheduler_rows) == 1
        assert scheduler_rows[0].source is SettingSource.ADMIN
        assert scheduler_rows[0].value.reconcile_interval_minutes == 30

    async def test_rejects_invalid_payload_before_upsert(
        self,
        runtime_settings_mock: AsyncMock,
    ) -> None:
        repo = _FakeRepo(rows=[])
        use_case = UpdateSettingUseCase(_FakeUoWFactory(repo), runtime_settings_mock)

        with pytest.raises(DomainValidationException):
            await use_case.execute(
                UpdateSettingInput(
                    key=SettingKey.INTRO_DETECTION.value,
                    value={"min_confidence": 5.0},  # out of [0, 1]
                    acting_admin_id="usr_admin",
                ),
            )

        assert repo.upserts == []
        runtime_settings_mock.invalidate.assert_not_called()

    async def test_rejects_unknown_key(
        self,
        runtime_settings_mock: AsyncMock,
    ) -> None:
        repo = _FakeRepo(rows=[])
        use_case = UpdateSettingUseCase(_FakeUoWFactory(repo), runtime_settings_mock)

        with pytest.raises(ValueError):
            await use_case.execute(
                UpdateSettingInput(
                    key="nonexistent",
                    value={},
                    acting_admin_id="usr_admin",
                ),
            )

        assert repo.upserts == []
        runtime_settings_mock.invalidate.assert_not_called()
