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
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.MOVIE,
            title=title,
            poster_path=poster_path,
        )

    return _factory


@pytest.fixture
def series_summary() -> MediaSummaryFactory:
    """Create a ``MediaSummary`` representing a series."""

    def _factory(
        media_id: str,
        title: str = "Test Series",
        poster_path: str | None = "https://image.tmdb.org/series.jpg",
    ) -> MediaSummary:
        return MediaSummary(
            media_id=media_id,
            media_type=MediaType.SERIES,
            title=title,
            poster_path=poster_path,
        )

    return _factory


def make_media_lookup_mock(*summaries: MediaSummary) -> AsyncMock:
    """Build an ``AsyncMock`` of ``MediaLookupPort`` returning ``summaries``."""
    mock = AsyncMock(spec=MediaLookupPort)
    mock.get_many.return_value = {(s.media_type, s.media_id): s for s in summaries}
    return mock
