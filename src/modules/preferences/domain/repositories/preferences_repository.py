"""Preferences repository interface."""

from abc import ABC, abstractmethod

from src.modules.preferences.domain.entities import PlaybackPreferences


class PreferencesRepository(ABC):
    """Read/persist playback preferences keyed by user."""

    @abstractmethod
    async def find_by_user_key(self, user_key: str) -> PlaybackPreferences | None:
        """Return the preferences record for ``user_key`` or ``None``.

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
