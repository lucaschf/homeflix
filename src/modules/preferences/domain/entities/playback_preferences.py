"""PlaybackPreferences aggregate root."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.preferences.domain.value_objects import (
    PreferencesId,
    Quality,
    Speed,
    SubtitleMode,
)

DEFAULT_USER_KEY = "default"
DEFAULT_AUDIO_LANG = "pt-BR"
DEFAULT_SUBTITLE_LANG = "pt-BR"
DEFAULT_SUBTITLE_MODE = SubtitleMode.FOREIGN_ONLY
DEFAULT_QUALITY = Quality.BEST
DEFAULT_SPEED = 1.0


class PlaybackPreferences(AggregateRoot[PreferencesId]):
    """Per-user playback defaults the video player applies on startup.

    Singleton-per-``user_key`` — there is exactly one record per user.
    Until an auth system lands the only key is ``"default"``; every
    browser session shares the same row.

    Languages are kept as plain strings (not ``LanguageCode``) because
    the frontend persists IETF tags like ``"pt-BR"``/``"en-US"`` that
    don't match the shared kernel's strict ISO 639-1 shape.

    Example:
        >>> prefs = PlaybackPreferences.default_for()
        >>> prefs.speed.value
        1.0
        >>> prefs.subtitle_mode
        <SubtitleMode.FOREIGN_ONLY: 'foreignOnly'>
    """

    id: PreferencesId | None = Field(default=None)

    user_key: str = DEFAULT_USER_KEY
    audio_lang: str = DEFAULT_AUDIO_LANG
    subtitle_lang: str = DEFAULT_SUBTITLE_LANG
    subtitle_mode: SubtitleMode = DEFAULT_SUBTITLE_MODE
    default_quality: Quality = DEFAULT_QUALITY
    speed: Speed = Field(default_factory=lambda: Speed(DEFAULT_SPEED))

    @field_validator("speed", mode="before")
    @classmethod
    def _coerce_speed(cls, value: Any) -> Speed:
        """Accept raw floats alongside ``Speed`` instances."""
        return value if isinstance(value, Speed) else Speed(value)

    @field_validator("subtitle_mode", mode="before")
    @classmethod
    def _coerce_subtitle_mode(cls, value: Any) -> SubtitleMode:
        """Accept the canonical string alongside ``SubtitleMode`` members."""
        return value if isinstance(value, SubtitleMode) else SubtitleMode(value)

    @field_validator("default_quality", mode="before")
    @classmethod
    def _coerce_quality(cls, value: Any) -> Quality:
        """Accept the canonical string alongside ``Quality`` members."""
        return value if isinstance(value, Quality) else Quality(value)

    @classmethod
    def default_for(cls, user_key: str = DEFAULT_USER_KEY) -> Self:
        """Build a fresh preferences record with all factory defaults."""
        return cls(
            id=PreferencesId.for_user_key(user_key),
            user_key=user_key,
        )

    def apply_updates(
        self,
        *,
        audio_lang: str | None = None,
        subtitle_lang: str | None = None,
        subtitle_mode: str | None = None,
        default_quality: str | None = None,
        speed: float | None = None,
    ) -> Self:
        """Return a copy with only the non-``None`` fields replaced.

        Invalid enum / range inputs raise ``DomainValidationException``
        at the field validators — the use case doesn't need to probe.
        """
        updates: dict[str, Any] = {}
        if audio_lang is not None:
            updates["audio_lang"] = audio_lang
        if subtitle_lang is not None:
            updates["subtitle_lang"] = subtitle_lang
        if subtitle_mode is not None:
            updates["subtitle_mode"] = subtitle_mode
        if default_quality is not None:
            updates["default_quality"] = default_quality
        if speed is not None:
            updates["speed"] = speed
        if not updates:
            return self
        return self.with_updates(**updates)


__all__ = [
    "DEFAULT_AUDIO_LANG",
    "DEFAULT_QUALITY",
    "DEFAULT_SPEED",
    "DEFAULT_SUBTITLE_LANG",
    "DEFAULT_SUBTITLE_MODE",
    "DEFAULT_USER_KEY",
    "PlaybackPreferences",
]
