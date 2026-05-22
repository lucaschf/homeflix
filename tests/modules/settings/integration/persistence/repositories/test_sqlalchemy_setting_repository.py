"""Integration tests for :class:`SQLAlchemySettingRepository`."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
)
from src.modules.settings.infrastructure.persistence.repositories import (
    SQLAlchemySettingRepository,
)


@pytest.mark.integration
class TestSQLAlchemySettingRepository:
    async def test_list_all_returns_empty_on_fresh_table(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySettingRepository(db_session)

        assert list(await repo.list_all()) == []

    async def test_find_by_key_returns_none_when_absent(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySettingRepository(db_session)

        assert await repo.find_by_key(SettingKey.SCHEDULER) is None

    async def test_upsert_inserts_then_replaces_same_key(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySettingRepository(db_session)
        seed = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=True, reconcile_interval_minutes=5),
            source=SettingSource.MIGRATION_SEED,
        )

        await repo.upsert(seed)

        admin_edit = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=False, reconcile_interval_minutes=15),
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin",
        )
        await repo.upsert(admin_edit)

        rows = list(await repo.list_all())
        assert len(rows) == 1
        only = rows[0]
        assert only.id is SettingKey.SCHEDULER
        assert isinstance(only.value, SchedulerConfig)
        assert only.value.enabled is False
        assert only.value.reconcile_interval_minutes == 15
        assert only.source is SettingSource.ADMIN
        assert only.updated_by_user_id == "usr_admin"

    async def test_upsert_preserves_polymorphic_value_type(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySettingRepository(db_session)

        await repo.upsert(
            Setting(
                id=SettingKey.INTRO_DETECTION,
                value=IntroDetectionConfig(enabled=True, min_confidence=0.8),
                source=SettingSource.ADMIN,
            )
        )

        loaded = await repo.find_by_key(SettingKey.INTRO_DETECTION)

        assert loaded is not None
        assert isinstance(loaded.value, IntroDetectionConfig)
        assert loaded.value.min_confidence == 0.8

    async def test_list_all_returns_each_key_once(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySettingRepository(db_session)

        await repo.upsert(
            Setting(
                id=SettingKey.SCHEDULER,
                value=SchedulerConfig(),
                source=SettingSource.MIGRATION_SEED,
            )
        )
        await repo.upsert(
            Setting(
                id=SettingKey.INTRO_DETECTION,
                value=IntroDetectionConfig(),
                source=SettingSource.MIGRATION_SEED,
            )
        )

        rows = list(await repo.list_all())

        assert {r.id for r in rows} == {
            SettingKey.SCHEDULER,
            SettingKey.INTRO_DETECTION,
        }
