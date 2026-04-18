"""Unit test fixtures and helpers for the collections bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWork,
    CollectionsUnitOfWorkFactory,
)
from src.modules.collections.domain.repositories import (
    CustomListRepository,
    WatchlistRepository,
)


@dataclass
class CollectionsUoWMocks:
    """Bundle of mocks produced by ``make_collections_uow_mock``."""

    factory: CollectionsUnitOfWorkFactory
    uow: CollectionsUnitOfWork
    watchlist: AsyncMock
    custom_lists: AsyncMock


def make_collections_uow_mock() -> CollectionsUoWMocks:
    """Build a mock :class:`CollectionsUnitOfWork` factory."""
    watchlist = AsyncMock(spec=WatchlistRepository)
    custom_lists = AsyncMock(spec=CustomListRepository)

    uow: CollectionsUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.watchlist = watchlist
    uow.custom_lists = custom_lists

    factory = MagicMock(return_value=uow)
    return CollectionsUoWMocks(
        factory=factory, uow=uow, watchlist=watchlist, custom_lists=custom_lists
    )
