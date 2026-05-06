"""Unit test fixtures and helpers for the watch_progress bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWork,
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


@dataclass
class WatchProgressUoWMocks:
    """Bundle of mocks produced by ``make_watch_progress_uow_mock``."""

    factory: WatchProgressUnitOfWorkFactory
    uow: WatchProgressUnitOfWork
    progress: AsyncMock


def make_watch_progress_uow_mock() -> WatchProgressUoWMocks:
    """Build a mock :class:`WatchProgressUnitOfWork` factory."""
    progress = AsyncMock(spec=WatchProgressRepository)
    uow: WatchProgressUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.progress = progress
    factory = MagicMock(return_value=uow)
    return WatchProgressUoWMocks(factory=factory, uow=uow, progress=progress)
