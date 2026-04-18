"""Watch Progress bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


class WatchProgressUnitOfWork(UnitOfWork):
    """Transactional boundary for WatchProgress writes."""

    progress: WatchProgressRepository


class WatchProgressUnitOfWorkFactory(ABC):
    """Builds fresh ``WatchProgressUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> WatchProgressUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["WatchProgressUnitOfWork", "WatchProgressUnitOfWorkFactory"]
