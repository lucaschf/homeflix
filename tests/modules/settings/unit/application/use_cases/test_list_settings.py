"""Unit tests for :class:`ListSettingsUseCase`."""

from collections.abc import Sequence
from typing import Self

import pytest

from src.modules.settings.application.unit_of_work import SettingsUnitOfWork
from src.modules.settings.application.use_cases import ListSettingsUseCase
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

    async def list_all(self) -> Sequence[Setting]:
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

    def __call__(self) -> _FakeUoW:
        return _FakeUoW(self.repo)


@pytest.mark.unit
class TestListSettings:
    async def test_returns_default_detail_for_every_bucket_when_table_empty(self) -> None:
        use_case = ListSettingsUseCase(_FakeUoWFactory(_FakeRepo(rows=[])))

        details = await use_case.execute()

        keys = [d.key for d in details]
        assert keys == [k.value for k in SettingKey]
        for detail in details:
            assert detail.source == "default"
            assert detail.updated_at is None
            assert detail.updated_by_user_id is None

    async def test_persisted_row_carries_admin_metadata(self) -> None:
        row = Setting(
            id=SettingKey.INTRO_DETECTION,
            value=IntroDetectionConfig(enabled=True, min_confidence=0.9),
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin0000000",
        )
        use_case = ListSettingsUseCase(_FakeUoWFactory(_FakeRepo(rows=[row])))

        details = await use_case.execute()

        intro = next(d for d in details if d.key == "intro_detection")
        assert intro.source == "admin"
        assert intro.updated_by_user_id == "usr_admin0000000"
        assert intro.updated_at is not None
        assert intro.value["min_confidence"] == 0.9
        assert intro.value["enabled"] is True

    async def test_unpersisted_buckets_still_fall_back_to_default(self) -> None:
        scheduler_row = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=False, reconcile_interval_minutes=99),
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin0000000",
        )
        use_case = ListSettingsUseCase(_FakeUoWFactory(_FakeRepo(rows=[scheduler_row])))

        details = await use_case.execute()

        scheduler = next(d for d in details if d.key == "scheduler")
        intro = next(d for d in details if d.key == "intro_detection")
        assert scheduler.source == "admin"
        assert intro.source == "default"
        assert intro.value == IntroDetectionConfig().model_dump(mode="json")
