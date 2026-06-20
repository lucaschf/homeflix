"""Unit test fixtures and helpers for the media bounded context.

Provides the small amount of shared scaffolding that more than one
unit test reaches for — chiefly a factory that builds a mock
``MediaUnitOfWork`` suitable for use as an async context manager.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.domain.repositories import (
    MediaConflictRepository,
    MovieRepository,
    SeriesRepository,
)


@dataclass
class MediaUoWMocks:
    """Bundle of mocks produced by ``make_media_uow_mock``.

    Attributes:
        factory: Callable matching ``MediaUnitOfWorkFactory``; returns ``uow``.
        uow: The mock ``MediaUnitOfWork`` — already configured as an async
            context manager returning itself on ``__aenter__``.
        movies: Mock ``MovieRepository`` exposed as ``uow.movies``.
        series: Mock ``SeriesRepository`` exposed as ``uow.series``.
        media_conflicts: Mock ``MediaConflictRepository`` exposed as
            ``uow.media_conflicts``.
    """

    factory: MediaUnitOfWorkFactory
    uow: MediaUnitOfWork
    movies: AsyncMock
    series: AsyncMock
    media_conflicts: AsyncMock


def make_media_uow_mock() -> MediaUoWMocks:
    """Build a mock :class:`MediaUnitOfWork` factory.

    The returned ``factory`` is callable and yields the same ``uow``
    every invocation — sufficient for tests that drive a single use
    case, and explicit enough that tests which care about multiple
    transactions can assert on ``factory.call_count``.
    """
    movies = AsyncMock(spec=MovieRepository)
    series = AsyncMock(spec=SeriesRepository)
    media_conflicts = AsyncMock(spec=MediaConflictRepository)

    # Empty-catalog defaults: path lookups miss unless a test wires them.
    # Without this, AsyncMock returns a truthy Mock and the scanner's
    # idempotency guard / title-fallback would treat every path as already
    # owned.
    movies.find_by_file_path.return_value = None
    series.find_by_file_path.return_value = None

    uow: MediaUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.movies = movies
    uow.series = series
    uow.media_conflicts = media_conflicts

    factory = MagicMock(return_value=uow)
    return MediaUoWMocks(
        factory=factory,
        uow=uow,
        movies=movies,
        series=series,
        media_conflicts=media_conflicts,
    )


class FakeProfileLibraryAccessPort(ProfileLibraryAccessPort):
    """In-memory implementation of ``ProfileLibraryAccessPort`` for tests.

    Stores a ``profile_id -> list[library_id]`` mapping and resolves
    ``find_for_profile`` against it. Unmapped profile ids resolve to
    an empty list — matching the production adapter's deny-all-on-miss
    semantics. Tests that want the inclusion path map the configured
    test profile to ``[_LIBRARY_ID]`` (``"lib_test12345678"``); tests
    that want the deny-all path map it to ``[]`` (or omit it
    entirely).
    """

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self._mapping: dict[str, list[str]] = dict(mapping) if mapping else {}

    def set(self, profile_id: str, library_ids: list[str]) -> None:
        """Set the allowed libraries for ``profile_id``."""
        self._mapping[profile_id] = list(library_ids)

    async def find_for_profile(self, profile_id: str) -> list[str]:
        return list(self._mapping.get(profile_id, []))


def make_profile_library_access(
    *,
    profile_id: str = "prf_test12345678",
    library_ids: list[str] | None = None,
) -> FakeProfileLibraryAccessPort:
    """Build a fake port bound to a single test profile.

    By default maps ``prf_test12345678`` to ``["lib_test12345678"]``,
    matching the constants used by the existing media unit tests.
    Passing ``library_ids=[]`` exercises the deny-all path.
    """
    if library_ids is None:
        library_ids = ["lib_test12345678"]
    return FakeProfileLibraryAccessPort({profile_id: list(library_ids)})
