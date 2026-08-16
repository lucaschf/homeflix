"""DTOs for playback preferences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.preferences.domain.entities import PlaybackPreferences


@dataclass(frozen=True)
class GetPreferencesInput:
    """Input for ``GetPreferencesUseCase``."""

    profile_id: str


@dataclass(frozen=True)
class SubtitleAppearanceDto:
    """Wire shape for the subtitle overlay styling."""

    color: str
    background: str
    font_size: str
    text_edge: str


@dataclass(frozen=True)
class PreferencesOutput:
    """Current playback preferences for the profile."""

    audio_lang: str
    subtitle_lang: str
    subtitle_mode: str
    default_quality: str
    speed: float
    subtitle_appearance: SubtitleAppearanceDto

    @classmethod
    def from_entity(cls, entity: PlaybackPreferences) -> PreferencesOutput:
        """Project the entity into the transport DTO."""
        appearance = entity.subtitle_appearance
        return cls(
            audio_lang=entity.audio_lang.value,
            subtitle_lang=entity.subtitle_lang.value,
            subtitle_mode=entity.subtitle_mode.value,
            default_quality=entity.default_quality.value,
            speed=entity.speed.value,
            subtitle_appearance=SubtitleAppearanceDto(
                color=appearance.color.value,
                background=appearance.background.value,
                font_size=appearance.font_size.value,
                text_edge=appearance.text_edge.value,
            ),
        )


@dataclass(frozen=True)
class UpdatePreferencesInput:
    """Partial update — only non-``None`` fields are applied.

    ``subtitle_appearance`` is itself a partial map (``color`` /
    ``background`` / ``font_size``): the entity merges whatever keys are
    present onto the current styling, so a client can change one knob.
    """

    profile_id: str
    audio_lang: str | None = None
    subtitle_lang: str | None = None
    subtitle_mode: str | None = None
    default_quality: str | None = None
    speed: float | None = None
    subtitle_appearance: dict[str, str] | None = None


__all__ = [
    "GetPreferencesInput",
    "PreferencesOutput",
    "SubtitleAppearanceDto",
    "UpdatePreferencesInput",
]
