"""Unit test fixtures and helpers for the media bounded context.

Provides the small amount of shared scaffolding that more than one
unit test reaches for — chiefly a factory that builds a mock
``MediaUnitOfWork`` suitable for use as an async context manager.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


@dataclass
class MediaUoWMocks:
    """Bundle of mocks produced by ``make_media_uow_mock``.

    Attributes:
        factory: Callable matching ``MediaUnitOfWorkFactory``; returns ``uow``.
        uow: The mock ``MediaUnitOfWork`` — already configured as an async
            context manager returning itself on ``__aenter__``.
        movies: Mock ``MovieRepository`` exposed as ``uow.movies``.
        series: Mock ``SeriesRepository`` exposed as ``uow.series``.
    """

    factory: MediaUnitOfWorkFactory
    uow: MediaUnitOfWork
    movies: AsyncMock
    series: AsyncMock


def make_media_uow_mock() -> MediaUoWMocks:
    """Build a mock :class:`MediaUnitOfWork` factory.

    The returned ``factory`` is callable and yields the same ``uow``
    every invocation — sufficient for tests that drive a single use
    case, and explicit enough that tests which care about multiple
    transactions can assert on ``factory.call_count``.
    """
    movies = AsyncMock(spec=MovieRepository)
    series = AsyncMock(spec=SeriesRepository)

    uow: MediaUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.movies = movies
    uow.series = series

    factory = MagicMock(return_value=uow)
    return MediaUoWMocks(factory=factory, uow=uow, movies=movies, series=series)
