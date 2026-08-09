"""Shared fixtures for collections use case tests."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.modules.collections.application.ports import (
    MediaLookupPort,
    MediaSummary,
    ProfileLibraryAccessPort,
    ProfileLookupPort,
    ProgressLookupPort,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.library_id import LibraryId

MediaSummaryFactory = Callable[..., MediaSummary]


@pytest.fixture
def movie_summary() -> MediaSummaryFactory:
    """Create a ``MediaSummary`` representing a movie."""

    def _factory(
        media_id: str,
        title: str = "Test Movie",
        poster_path: str | None = "https://image.tmdb.org/poster.jpg",
        year: int | None = 2010,
        runtime_seconds: int | None = 8880,
        genres: tuple[str, ...] = ("Action", "Sci-Fi"),
        resolution: str | None = "4K",
        hdr: bool = True,
        library_id: str | None = "lib_movies00001",
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.MOVIE,
            title=title,
            poster_path=poster_path,
            year=year,
            runtime_seconds=runtime_seconds,
            genres=genres,
            resolution=resolution,
            hdr=hdr,
            library_id=library_id,
        )

    return _factory


@pytest.fixture
def series_summary() -> MediaSummaryFactory:
    """Create a ``MediaSummary`` representing a series."""

    def _factory(
        media_id: str,
        title: str = "Test Series",
        poster_path: str | None = "https://image.tmdb.org/series.jpg",
        year: int | None = 2008,
        genres: tuple[str, ...] = ("Drama",),
        library_id: str | None = "lib_series00001",
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.SERIES,
            title=title,
            poster_path=poster_path,
            year=year,
            genres=genres,
            library_id=library_id,
        )

    return _factory


def make_media_lookup_mock(*summaries: MediaSummary) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` returning ``summaries``."""
    mock = AsyncMock(spec=MediaLookupPort)
    mock.get_many.return_value = {(s.media_type, s.media_id): s for s in summaries}
    return mock


def make_progress_lookup_mock(progress: dict[str, float] | None = None) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProgressLookupPort`` returning ``progress``."""
    mock = AsyncMock(spec=ProgressLookupPort)
    mock.get_progress.return_value = progress or {}
    return mock


def make_profile_library_access_mock(*library_ids: str) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProfileLibraryAccessPort``.

    Returns the given library ids (as typed ``LibraryId``) for any
    profile. An empty call means deny-all.
    """
    mock = AsyncMock(spec=ProfileLibraryAccessPort)
    mock.find_for_profile.return_value = [LibraryId(lib) for lib in library_ids]
    return mock


def make_profile_lookup_mock(names: dict[str, str] | None = None) -> AsyncMock:
    """Build an ``AsyncMock`` of ``ProfileLookupPort`` returning ``names``."""
    mock = AsyncMock(spec=ProfileLookupPort)
    mock.get_names.return_value = names or {}
    return mock
