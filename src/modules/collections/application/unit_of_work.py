"""Collections bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.collections.domain.repositories import (
    CustomListRepository,
    WatchlistRepository,
)


class CollectionsUnitOfWork(UnitOfWork):
    """Transactional boundary for Watchlist and Custom List writes."""

    watchlist: WatchlistRepository
    custom_lists: CustomListRepository


class CollectionsUnitOfWorkFactory(ABC):
    """Builds fresh ``CollectionsUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> CollectionsUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["CollectionsUnitOfWork", "CollectionsUnitOfWorkFactory"]
