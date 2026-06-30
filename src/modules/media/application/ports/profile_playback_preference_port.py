"""Port for reading a profile's playback preference from the Preferences BC.

ADR-026 makes the server the authority for the default audio/subtitle
track, resolved from the *per-user* preference (the Preferences BC), not
per-library settings. This port exposes the slice the track selector needs
so Media never imports the Preferences aggregate or its Unit of Work above
the adapter (ADR-009). The adapter lives in ``media.infrastructure.acl``.

Phase 2 consumes only ``audio_language`` (the ``/tracks`` audio default).
``subtitle_language`` / ``subtitle_mode`` are added when ``select_subtitle``
moves server-side (ADR-026 phase 4).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.shared_kernel.value_objects.language_code import LanguageCode


@dataclass(frozen=True)
class PlaybackPreference:
    """Consumer-owned projection of a profile's playback preference.

    Attributes:
        audio_language: The profile's preferred audio language as a strict
            ISO 639-1 :class:`LanguageCode` (the base subtag of the stored
            IETF tag, e.g. ``pt-BR`` → ``pt``), matched against a media
            track's language. ``None`` when the stored tag has no usable
            ISO 639-1 base — the selector then applies no preference.
    """

    audio_language: LanguageCode | None


class ProfilePlaybackPreferencePort(ABC):
    """Read a profile's playback preference without the Preferences aggregate."""

    @abstractmethod
    async def for_profile(self, profile_id: str) -> PlaybackPreference:
        """Return the profile's playback preference.

        Mirrors the Preferences BC's own default-on-absent behavior: a
        profile that never saved preferences resolves to the factory
        defaults (so server-side selection matches what the client would
        apply), never an empty result.

        Args:
            profile_id: Prefixed external id (``prf_xxx``).

        Returns:
            A :class:`PlaybackPreference` (defaults applied when absent).
        """
        ...


__all__ = ["PlaybackPreference", "ProfilePlaybackPreferencePort"]
