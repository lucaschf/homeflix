"""Shared fixtures for collections use case tests."""

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.modules.collections.application.ports import MediaLookupPort, MediaSummary
from src.shared_kernel.value_objects import MediaType

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
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.SERIES,
            title=title,
            poster_path=poster_path,
            year=year,
            genres=genres,
        )

    return _factory


def make_media_lookup_mock(*summaries: MediaSummary) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` returning ``summaries``."""
    mock = AsyncMock(spec=MediaLookupPort)
    mock.get_many.return_value = {(s.media_type, s.media_id): s for s in summaries}
    return mock
