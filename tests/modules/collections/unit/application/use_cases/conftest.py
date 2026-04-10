"""Shared fixtures for collections use case tests."""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

MediaMockFactory = Callable[..., MagicMock]


@pytest.fixture
def movie_mock() -> MediaMockFactory:
    """Create a mock movie entity with default values."""

    def _factory(media_id: str, title: str = "Test Movie") -> MagicMock:
        movie = MagicMock()
        movie.id = media_id
        movie.get_title.return_value = title
        movie.poster_path = MagicMock(value="https://image.tmdb.org/poster.jpg")
        return movie

    return _factory


@pytest.fixture
def series_mock() -> MediaMockFactory:
    """Create a mock series entity with default values."""

    def _factory(media_id: str, title: str = "Test Series") -> MagicMock:
        series = MagicMock()
        series.id = media_id
        series.get_title.return_value = title
        series.poster_path = MagicMock(value="https://image.tmdb.org/series.jpg")
        return series

    return _factory
