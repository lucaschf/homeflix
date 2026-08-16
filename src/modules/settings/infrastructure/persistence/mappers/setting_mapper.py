"""Bidirectional mapper between :class:`Setting` and :class:`SettingModel`."""

from typing import Any, cast

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    ConfigVO,
    SettingKey,
    SettingSource,
    vo_type_for,
)
from src.modules.settings.infrastructure.persistence.models import SettingModel


class SettingMapper:
    """Map between :class:`Setting` domain entity and ORM model.

    The mapper owns the polymorphic deserialization: it inspects
    ``model.key`` to pick the correct ``ConfigVO`` subtype — via the
    domain's ``setting_vo_registry`` — and rehydrates the row's
    ``value_json`` into it.

    Example:
        >>> model = SettingMapper.to_model(setting)
        >>> setting = SettingMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: Setting) -> SettingModel:
        """Convert :class:`Setting` to ORM model."""
        return SettingModel(
            key=entity.id.value,
            value_json=entity.value.model_dump(mode="json"),
            source=entity.source.value,
            updated_by_user_id=entity.updated_by_user_id,
        )

    @staticmethod
    def to_entity(model: SettingModel) -> Setting:
        """Convert ORM model to :class:`Setting` entity.

        Raises:
            ValueError: When ``model.key`` is not a known
                :class:`SettingKey`.
        """
        key = SettingKey(model.key)
        vo_type = vo_type_for(key)
        payload: dict[str, Any] = dict(model.value_json or {})
        # vo_type_for(key) returns the concrete ConfigVO subtype for this key;
        # model_validate yields that subtype, which mypy widens to the union.
        value = cast(ConfigVO, vo_type.model_validate(payload))
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
