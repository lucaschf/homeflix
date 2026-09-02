"""PlaybackPreferences aggregate root."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.preferences.domain.value_objects import (
    CreditsSkipMode,
    IntroSkipMode,
    PreferencesId,
    Quality,
    Speed,
    SubtitleAppearance,
    SubtitleMode,
)
from src.shared_kernel.value_objects.language_tag import LanguageTag
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001

DEFAULT_AUDIO_LANG = "pt-BR"
DEFAULT_SUBTITLE_LANG = "pt-BR"
DEFAULT_SUBTITLE_MODE = SubtitleMode.FOREIGN_ONLY
DEFAULT_QUALITY = Quality.BEST
DEFAULT_SPEED = 1.0
DEFAULT_INTRO_SKIP_MODE = IntroSkipMode.MANUAL
DEFAULT_CREDITS_SKIP_MODE = CreditsSkipMode.MANUAL


class PlaybackPreferences(AggregateRoot[PreferencesId]):
    """Per-profile playback defaults the video player applies on startup.

    Singleton-per-``profile_id`` — there is exactly one record per
    profile. The row's external_id mirrors the owning profile id so
    the natural key (``profile_id``) and the surrogate identity
    (``PreferencesId``) stay in lockstep without an extra mapping
    table.

    Languages are :class:`LanguageTag` (IETF tags like ``"pt-BR"`` /
    ``"en-US"``) rather than the strict ISO 639-1 ``LanguageCode`` used
    for media tracks: the player persists region-qualified tags that the
    strict code rejects. The tag is still validated on write, so garbage
    can't round-trip to the database or out to the client.

    ``intro_skip_mode`` and ``credits_skip_mode`` are advisory: the
    server has no playhead, so it publishes the episode's markers (Media
    BC) alongside the preference and the player is what actually seeks.
    Both default to ``MANUAL``, which is today's behaviour — a button
    the viewer presses — so no existing profile changes until someone
    opts in.

    Example:
        >>> profile = ProfileId("prf_test12345678")
        >>> prefs = PlaybackPreferences.default_for(profile)
        >>> prefs.speed.value
        1.0
        >>> prefs.subtitle_mode
        <SubtitleMode.FOREIGN_ONLY: 'foreignOnly'>
    """

    id: PreferencesId | None = Field(default=None)

    profile_id: ProfileId
    audio_lang: LanguageTag = Field(default_factory=lambda: LanguageTag(DEFAULT_AUDIO_LANG))
    subtitle_lang: LanguageTag = Field(default_factory=lambda: LanguageTag(DEFAULT_SUBTITLE_LANG))
    subtitle_mode: SubtitleMode = DEFAULT_SUBTITLE_MODE
    default_quality: Quality = DEFAULT_QUALITY
    speed: Speed = Field(default_factory=lambda: Speed(DEFAULT_SPEED))
    subtitle_appearance: SubtitleAppearance = Field(default_factory=SubtitleAppearance.default)
    intro_skip_mode: IntroSkipMode = DEFAULT_INTRO_SKIP_MODE
    credits_skip_mode: CreditsSkipMode = DEFAULT_CREDITS_SKIP_MODE

    @field_validator("audio_lang", "subtitle_lang", mode="before")
    @classmethod
    def _coerce_language_tag(cls, value: Any) -> LanguageTag:
        """Accept raw IETF strings alongside ``LanguageTag`` instances."""
        return value if isinstance(value, LanguageTag) else LanguageTag(value)

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

    @field_validator("intro_skip_mode", mode="before")
    @classmethod
    def _coerce_intro_skip_mode(cls, value: Any) -> IntroSkipMode:
        """Accept the canonical string alongside ``IntroSkipMode`` members."""
        return value if isinstance(value, IntroSkipMode) else IntroSkipMode(value)

    @field_validator("credits_skip_mode", mode="before")
    @classmethod
    def _coerce_credits_skip_mode(cls, value: Any) -> CreditsSkipMode:
        """Accept the canonical string alongside ``CreditsSkipMode`` members."""
        return value if isinstance(value, CreditsSkipMode) else CreditsSkipMode(value)

    @classmethod
    def default_for(cls, profile_id: ProfileId) -> Self:
        """Build a fresh preferences record with all factory defaults."""
        return cls(
            id=PreferencesId.for_profile(profile_id),
            profile_id=profile_id,
        )

    def apply_updates(
        self,
        *,
        audio_lang: str | None = None,
        subtitle_lang: str | None = None,
        subtitle_mode: str | None = None,
        default_quality: str | None = None,
        speed: float | None = None,
        subtitle_appearance: dict[str, Any] | None = None,
        intro_skip_mode: str | None = None,
        credits_skip_mode: str | None = None,
    ) -> Self:
        """Return a copy with only the non-``None`` fields replaced.

        ``subtitle_appearance`` is merged field-by-field onto the current
        value, so a client can change just the color and keep the rest.
        Invalid enum / range / color inputs raise ``DomainValidationException``
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
        if subtitle_appearance is not None:
            merged = self.subtitle_appearance.model_dump(mode="json")
            merged.update(subtitle_appearance)
            updates["subtitle_appearance"] = merged
        if intro_skip_mode is not None:
            updates["intro_skip_mode"] = intro_skip_mode
        if credits_skip_mode is not None:
            updates["credits_skip_mode"] = credits_skip_mode
        if not updates:
            return self
        return self.with_updates(**updates)


__all__ = [
    "DEFAULT_AUDIO_LANG",
    "DEFAULT_CREDITS_SKIP_MODE",
    "DEFAULT_INTRO_SKIP_MODE",
    "DEFAULT_QUALITY",
    "DEFAULT_SPEED",
    "DEFAULT_SUBTITLE_LANG",
    "DEFAULT_SUBTITLE_MODE",
    "PlaybackPreferences",
]
