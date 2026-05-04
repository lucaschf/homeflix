"""Preferences repository interface."""

from abc import ABC, abstractmethod

from src.modules.preferences.domain.entities import PlaybackPreferences
from src.shared_kernel.value_objects.profile_id import ProfileId


class PreferencesRepository(ABC):
    """Read/persist playback preferences keyed by profile."""

    @abstractmethod
    async def find_by_profile_id(self, profile_id: ProfileId) -> PlaybackPreferences | None:
        """Return the preferences record for ``profile_id`` or ``None``.

        A ``None`` result is expected and normal on first access — the
        caller typically falls back to ``PlaybackPreferences.default_for``.
        """
        ...

    @abstractmethod
    async def save(self, preferences: PlaybackPreferences) -> PlaybackPreferences:
        """Create or update the preferences record.

        Returns the persisted entity (with server-generated
        timestamps refreshed).
        """
        ...


__all__ = ["PreferencesRepository"]
