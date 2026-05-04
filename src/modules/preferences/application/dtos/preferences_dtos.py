"""DTOs for playback preferences."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetPreferencesInput:
    """Input for ``GetPreferencesUseCase``."""

    profile_id: str


@dataclass(frozen=True)
class PreferencesOutput:
    """Current playback preferences for the profile."""

    audio_lang: str
    subtitle_lang: str
    subtitle_mode: str
    default_quality: str
    speed: float


@dataclass(frozen=True)
class UpdatePreferencesInput:
    """Partial update — only non-``None`` fields are applied."""

    profile_id: str
    audio_lang: str | None = None
    subtitle_lang: str | None = None
    subtitle_mode: str | None = None
    default_quality: str | None = None
    speed: float | None = None


__all__ = ["GetPreferencesInput", "PreferencesOutput", "UpdatePreferencesInput"]
