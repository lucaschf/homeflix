"""Settings bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.settings.domain.repositories import SettingRepository


class SettingsUnitOfWork(UnitOfWork):
    """Transactional boundary for setting upserts.

    Phase 1 (ADR-013) only needs writes to upsert migration seeds and,
    later, admin-panel edits. Reads from the :class:`RuntimeSettings`
    facade open their own short-lived session and bypass this UoW.
    """

    settings: SettingRepository


class SettingsUnitOfWorkFactory(ABC):
    """Builds fresh :class:`SettingsUnitOfWork` instances on demand."""

    @abstractmethod
    def __call__(self) -> SettingsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["SettingsUnitOfWork", "SettingsUnitOfWorkFactory"]
