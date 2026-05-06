"""Unit test fixtures and helpers for the library bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.library.application.unit_of_work import (
    LibraryUnitOfWork,
    LibraryUnitOfWorkFactory,
)
from src.modules.library.domain.repositories.library_repository import LibraryRepository


@dataclass
class LibraryUoWMocks:
    """Bundle of mocks produced by ``make_library_uow_mock``.

    Attributes:
        factory: Callable matching ``LibraryUnitOfWorkFactory``; returns ``uow``.
        uow: The mock ``LibraryUnitOfWork`` — an async context manager returning itself.
        libraries: Mock ``LibraryRepository`` exposed as ``uow.libraries``.
    """

    factory: LibraryUnitOfWorkFactory
    uow: LibraryUnitOfWork
    libraries: AsyncMock


def make_library_uow_mock() -> LibraryUoWMocks:
    """Build a mock :class:`LibraryUnitOfWork` factory."""
    libraries = AsyncMock(spec=LibraryRepository)
    uow: LibraryUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.libraries = libraries
    factory = MagicMock(return_value=uow)
    return LibraryUoWMocks(factory=factory, uow=uow, libraries=libraries)
