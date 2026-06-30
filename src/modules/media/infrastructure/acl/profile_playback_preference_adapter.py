"""Adapter implementing ``ProfilePlaybackPreferencePort`` via the Preferences UoW.

Keeps the cross-BC read behind the abstract port: the ``/tracks`` use case
sees only the port, while this adapter is the single place Media touches the
Preferences BC to read playback preferences (ADR-026 / ADR-009).
"""

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.application.ports.profile_playback_preference_port import (
    PlaybackPreference,
    ProfilePlaybackPreferencePort,
)
from src.modules.preferences.application.unit_of_work import PreferencesUnitOfWorkFactory
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.language_tag import LanguageTag
from src.shared_kernel.value_objects.profile_id import ProfileId


def _to_language_code(tag: LanguageTag) -> LanguageCode | None:
    """Bridge a preference's IETF tag to a track's strict ISO 639-1 code.

    Compares on the primary subtag (``pt-BR`` → ``pt``), as documented on
    :attr:`LanguageTag.primary_subtag`. Returns ``None`` when the primary
    subtag is not a valid ISO 639-1 code (e.g. a 3-letter tag) so the
    caller applies no audio preference rather than raising.
    """
    try:
        return LanguageCode(tag.primary_subtag)
    except DomainValidationException:
        return None


class ProfilePlaybackPreferenceAdapter(ProfilePlaybackPreferencePort):
    """Resolve a profile's playback preference through the Preferences UoW."""

    def __init__(self, preferences_uow_factory: PreferencesUnitOfWorkFactory) -> None:
        self._preferences_uow_factory = preferences_uow_factory

    async def for_profile(self, profile_id: str) -> PlaybackPreference:
        """Load the profile's preferences (defaulting on first access)."""
        pid = ProfileId(profile_id)
        async with self._preferences_uow_factory() as uow:
            prefs = await uow.preferences.find_by_profile_id(pid)
        # Match GetPreferencesUseCase: absent row → factory defaults, so the
        # server resolves the same default the client would apply.
        if prefs is None:
            prefs = PlaybackPreferences.default_for(pid)
        return PlaybackPreference(audio_language=_to_language_code(prefs.audio_lang))


__all__ = ["ProfilePlaybackPreferenceAdapter"]
