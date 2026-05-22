"""Unit tests for the :class:`Setting` aggregate."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
    StreamingConfig,
    ThumbnailBackfillConfig,
)


class TestSettingValueMatchesKey:
    def test_construction_with_matching_value_succeeds(self) -> None:
        setting = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(),
            source=SettingSource.MIGRATION_SEED,
        )

        assert setting.id is SettingKey.SCHEDULER
        assert isinstance(setting.value, SchedulerConfig)

    @pytest.mark.parametrize(
        ("key", "wrong_value_factory"),
        [
            (SettingKey.SCHEDULER, IntroDetectionConfig),
            (SettingKey.THUMBNAIL_BACKFILL, SchedulerConfig),
            (SettingKey.INTRO_DETECTION, ThumbnailBackfillConfig),
            (SettingKey.STREAMING, AvatarConfig),
            (SettingKey.AVATAR, StreamingConfig),
        ],
    )
    def test_construction_with_mismatched_value_raises(
        self,
        key: SettingKey,
        wrong_value_factory: type,
    ) -> None:
        with pytest.raises(DomainValidationException):
            Setting(
                id=key,
                value=wrong_value_factory(),
                source=SettingSource.MIGRATION_SEED,
            )


class TestSettingWithUpdates:
    def test_with_updates_replaces_value_and_bumps_timestamp(self) -> None:
        original = Setting(
            id=SettingKey.INTRO_DETECTION,
            value=IntroDetectionConfig(),
            source=SettingSource.MIGRATION_SEED,
        )

        updated_value = original.value.with_updates(min_confidence=0.9)
        updated = original.with_updates(
            value=updated_value,
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin",
        )

        assert updated.value.min_confidence == 0.9
        assert updated.source is SettingSource.ADMIN
        assert updated.updated_by_user_id == "usr_admin"
        assert updated.updated_at >= original.updated_at

    def test_with_updates_rejects_mismatched_value_type(self) -> None:
        setting = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(),
            source=SettingSource.MIGRATION_SEED,
        )

        with pytest.raises(DomainValidationException):
            setting.with_updates(value=IntroDetectionConfig())
