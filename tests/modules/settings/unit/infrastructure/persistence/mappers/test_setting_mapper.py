"""Unit tests for :class:`SettingMapper`."""

from datetime import UTC, datetime

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
)
from src.modules.settings.infrastructure.persistence.mappers import SettingMapper
from src.modules.settings.infrastructure.persistence.models import SettingModel


class TestSettingMapper:
    def test_to_model_serializes_value_to_json(self) -> None:
        setting = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=False, reconcile_interval_minutes=15),
            source=SettingSource.MIGRATION_SEED,
        )

        model = SettingMapper.to_model(setting)

        assert model.key == "scheduler"
        assert model.value_json == {
            "enabled": False,
            "reconcile_interval_minutes": 15,
        }
        assert model.source == "migration_seed"
        assert model.updated_by_user_id is None

    def test_to_entity_round_trips_value_and_metadata(self) -> None:
        now = datetime.now(UTC)
        model = SettingModel(
            key="intro_detection",
            value_json={
                "enabled": True,
                "batch_size": 2,
                "interval_minutes": 30,
                "audio_window_seconds": 600,
                "min_confidence": 0.85,
                "max_hash_hamming": 10,
                "tolerance_hashes": 2,
                "min_intro_seconds": 5.0,
                "max_intro_seconds": 120.0,
            },
            source="admin",
            updated_by_user_id="usr_alice",
        )
        model.created_at = now
        model.updated_at = now

        entity = SettingMapper.to_entity(model)

        assert isinstance(entity, Setting)
        assert entity.id is SettingKey.INTRO_DETECTION
        assert isinstance(entity.value, IntroDetectionConfig)
        assert entity.value.min_confidence == 0.85
        assert entity.source is SettingSource.ADMIN
        assert entity.updated_by_user_id == "usr_alice"
        assert entity.created_at == now
        assert entity.updated_at == now

    def test_round_trip_preserves_avatar_config(self) -> None:
        now = datetime.now(UTC)
        original = Setting(
            id=SettingKey.AVATAR,
            value=AvatarConfig(max_size_mb=5, size_pixels=512),
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin",
        )
        model = SettingMapper.to_model(original)
        model.created_at = now
        model.updated_at = now

        back = SettingMapper.to_entity(model)

        assert back.id is SettingKey.AVATAR
        assert isinstance(back.value, AvatarConfig)
        assert back.value.max_size_mb == 5
        assert back.value.size_pixels == 512

    def test_update_model_mutates_value_and_audit_fields(self) -> None:
        now = datetime.now(UTC)
        model = SettingModel(
            key="scheduler",
            value_json={"enabled": True, "reconcile_interval_minutes": 5},
            source="migration_seed",
            updated_by_user_id=None,
        )
        model.created_at = now
        model.updated_at = now

        updated_entity = Setting(
            id=SettingKey.SCHEDULER,
            value=SchedulerConfig(enabled=False, reconcile_interval_minutes=20),
            source=SettingSource.ADMIN,
            updated_by_user_id="usr_admin",
        )

        SettingMapper.update_model(model, updated_entity)

        assert model.key == "scheduler"
        assert model.value_json == {
            "enabled": False,
            "reconcile_interval_minutes": 20,
        }
        assert model.source == "admin"
        assert model.updated_by_user_id == "usr_admin"
