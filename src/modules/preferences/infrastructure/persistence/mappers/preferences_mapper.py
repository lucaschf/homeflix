"""Mapper between PlaybackPreferences and its ORM row."""

from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.value_objects import (
    PreferencesId,
    Quality,
    Speed,
    SubtitleAppearance,
    SubtitleMode,
)
from src.modules.preferences.infrastructure.persistence.models.preferences_model import (
    PreferencesModel,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


class PreferencesMapper:
    """Bidirectional mapper between the entity and the ORM model."""

    @staticmethod
    def to_entity(model: PreferencesModel) -> PlaybackPreferences:
        """Project a row into a fully-validated ``PlaybackPreferences``."""
        return PlaybackPreferences(
            id=PreferencesId(model.external_id),
            profile_id=ProfileId(model.profile_id),
            audio_lang=model.audio_lang,
            subtitle_lang=model.subtitle_lang,
            subtitle_mode=SubtitleMode(model.subtitle_mode),
            default_quality=Quality(model.default_quality),
            speed=Speed(model.speed),
            subtitle_appearance=SubtitleAppearance(
                color=model.subtitle_color,
                background=model.subtitle_background,
                font_size=model.subtitle_font_size,
                text_edge=model.subtitle_text_edge,
            ),
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
            profile_id=str(entity.profile_id),
            audio_lang=entity.audio_lang.value,
            subtitle_lang=entity.subtitle_lang.value,
            subtitle_mode=entity.subtitle_mode.value,
            default_quality=entity.default_quality.value,
            speed=entity.speed.value,
            subtitle_color=entity.subtitle_appearance.color.value,
            subtitle_background=entity.subtitle_appearance.background.value,
            subtitle_font_size=entity.subtitle_appearance.font_size.value,
            subtitle_text_edge=entity.subtitle_appearance.text_edge.value,
        )

    @staticmethod
    def update_model(
        model: PreferencesModel,
        entity: PlaybackPreferences,
    ) -> PreferencesModel:
        """Refresh the mutable fields on an existing row.

        ``profile_id`` is not touched — the caller used it to locate
        ``model`` in the first place, and it's part of the singleton
        invariant enforced by the unique index.
        """
        model.audio_lang = entity.audio_lang.value
        model.subtitle_lang = entity.subtitle_lang.value
        model.subtitle_mode = entity.subtitle_mode.value
        model.default_quality = entity.default_quality.value
        model.speed = entity.speed.value
        model.subtitle_color = entity.subtitle_appearance.color.value
        model.subtitle_background = entity.subtitle_appearance.background.value
        model.subtitle_font_size = entity.subtitle_appearance.font_size.value
        model.subtitle_text_edge = entity.subtitle_appearance.text_edge.value
        return model


__all__ = ["PreferencesMapper"]
