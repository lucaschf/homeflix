"""Integration tests for :class:`RuntimeSettings` end-to-end against SQLite."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
)
from src.modules.settings.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemySettingsUnitOfWorkFactory,
)
from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


async def _seed_row(
    uow_factory: SqlAlchemySettingsUnitOfWorkFactory,
    setting: Setting,
) -> None:
    async with uow_factory() as uow:
        await uow.settings.upsert(setting)


@pytest.mark.integration
class TestRuntimeSettingsIntegration:
    async def test_defaults_when_table_empty(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow_factory = SqlAlchemySettingsUnitOfWorkFactory(session_factory)
        rs = RuntimeSettings(uow_factory)

        assert (await rs.scheduler()) == SchedulerConfig()
        assert (await rs.intro_detection()) == IntroDetectionConfig()

    async def test_db_row_overrides_after_refresh(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        uow_factory = SqlAlchemySettingsUnitOfWorkFactory(session_factory)
        rs = RuntimeSettings(uow_factory, cache_ttl_seconds=300)

        # Prime cache with defaults
        assert (await rs.scheduler()).enabled is True

        await _seed_row(
            uow_factory,
            Setting(
                id=SettingKey.SCHEDULER,
                value=SchedulerConfig(enabled=False, reconcile_interval_minutes=42),
                source=SettingSource.ADMIN,
                updated_by_user_id="usr_admin0000000",
            ),
        )

        await rs.invalidate()

        scheduler = await rs.scheduler()
        assert scheduler.enabled is False
        assert scheduler.reconcile_interval_minutes == 42
