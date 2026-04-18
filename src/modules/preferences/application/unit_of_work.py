"""Preferences bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.preferences.domain.repositories import PreferencesRepository


class PreferencesUnitOfWork(UnitOfWork):
    """Transactional boundary for Playback Preferences writes."""

    preferences: PreferencesRepository


class PreferencesUnitOfWorkFactory(ABC):
    """Builds fresh ``PreferencesUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> PreferencesUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["PreferencesUnitOfWork", "PreferencesUnitOfWorkFactory"]
