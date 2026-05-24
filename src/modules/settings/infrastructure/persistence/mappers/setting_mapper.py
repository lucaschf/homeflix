"""Bidirectional mapper between :class:`Setting` and :class:`SettingModel`."""

from typing import Any, ClassVar

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    ConfigVO,
    IntroDetectionConfig,
    ScanDedupConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
    StreamingConfig,
    ThumbnailBackfillConfig,
)
from src.modules.settings.infrastructure.persistence.models import SettingModel


class SettingMapper:
    """Map between :class:`Setting` domain entity and ORM model.

    The mapper owns the polymorphic deserialization: it inspects
    ``model.key`` to pick the correct ``ConfigVO`` subtype and
    rehydrates the row's ``value_json`` into it.

    Example:
        >>> model = SettingMapper.to_model(setting)
        >>> setting = SettingMapper.to_entity(model)
    """

    _KEY_TO_VO_TYPE: ClassVar[dict[SettingKey, type[CompoundValueObject]]] = {
        SettingKey.SCHEDULER: SchedulerConfig,
        SettingKey.THUMBNAIL_BACKFILL: ThumbnailBackfillConfig,
        SettingKey.INTRO_DETECTION: IntroDetectionConfig,
        SettingKey.STREAMING: StreamingConfig,
        SettingKey.AVATAR: AvatarConfig,
        SettingKey.SCAN_DEDUP: ScanDedupConfig,
    }

    @staticmethod
    def to_model(entity: Setting) -> SettingModel:
        """Convert :class:`Setting` to ORM model."""
        return SettingModel(
            key=entity.id.value,
            value_json=entity.value.model_dump(mode="json"),
            source=entity.source.value,
            updated_by_user_id=entity.updated_by_user_id,
        )

    @classmethod
    def to_entity(cls, model: SettingModel) -> Setting:
        """Convert ORM model to :class:`Setting` entity.

        Raises:
            ValueError: When ``model.key`` is not a known
                :class:`SettingKey`.
        """
        key = SettingKey(model.key)
        vo_type = cls._KEY_TO_VO_TYPE[key]
        payload: dict[str, Any] = dict(model.value_json or {})
        value: ConfigVO = vo_type.model_validate(payload)  # type: ignore[assignment]
        return Setting(
            id=key,
            value=value,
            source=SettingSource(model.source),
            updated_by_user_id=model.updated_by_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: SettingModel, entity: Setting) -> SettingModel:
        """Update an existing ORM model in-place with entity data.

        Mutates the model's ``value_json``, ``source``, and
        ``updated_by_user_id``. ``key`` is the primary key and is
        never updated.
        """
        model.value_json = entity.value.model_dump(mode="json")
        model.source = entity.source.value
        model.updated_by_user_id = entity.updated_by_user_id
        return model


__all__ = ["SettingMapper"]
