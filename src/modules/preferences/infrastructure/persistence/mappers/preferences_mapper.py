"""Mapper between PlaybackPreferences and its ORM row."""

from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import (
    PreferencesId,
    Quality,
    Speed,
    SubtitleMode,
)
from src.modules.preferences.infrastructure.persistence.models.preferences_model import (
    PreferencesModel,
)


class PreferencesMapper:
    """Bidirectional mapper between the entity and the ORM model."""

    @staticmethod
    def to_entity(model: PreferencesModel) -> PlaybackPreferences:
        """Project a row into a fully-validated ``PlaybackPreferences``."""
        return PlaybackPreferences(
            id=PreferencesId(model.external_id),
            user_key=model.user_key,
            audio_lang=model.audio_lang,
            subtitle_lang=model.subtitle_lang,
            subtitle_mode=SubtitleMode(model.subtitle_mode),
            default_quality=Quality(model.default_quality),
            speed=Speed(model.speed),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def new_model(entity: PlaybackPreferences) -> PreferencesModel:
        """Build a brand-new ORM row for an entity with no DB identity yet."""
        if entity.id is None:
            msg = "Cannot map entity without id to a new model"
            raise ValueError(msg)
        return PreferencesModel(
            external_id=str(entity.id),
            user_key=entity.user_key,
            audio_lang=entity.audio_lang,
            subtitle_lang=entity.subtitle_lang,
            subtitle_mode=entity.subtitle_mode.value,
            default_quality=entity.default_quality.value,
            speed=entity.speed.value,
        )

    @staticmethod
    def update_model(
        model: PreferencesModel,
        entity: PlaybackPreferences,
    ) -> PreferencesModel:
        """Copy mutable fields from the entity into an existing row."""
        model.audio_lang = entity.audio_lang
        model.subtitle_lang = entity.subtitle_lang
        model.subtitle_mode = entity.subtitle_mode.value
        model.default_quality = entity.default_quality.value
        model.speed = entity.speed.value
        return model


__all__ = ["PreferencesMapper"]
