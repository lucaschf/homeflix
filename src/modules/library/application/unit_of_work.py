"""Library bounded-context Unit of Work interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.library.domain.repositories.library_repository import LibraryRepository


class LibraryUnitOfWork(UnitOfWork):
    """Transactional boundary for Library aggregate operations.

    Subclasses populate ``libraries`` on ``__aenter__`` so writes within
    the same ``async with`` block share a transaction.
    """

    libraries: LibraryRepository


class LibraryUnitOfWorkFactory(ABC):
    """Builds fresh ``LibraryUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> LibraryUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["LibraryUnitOfWork", "LibraryUnitOfWorkFactory"]
