"""Tests for GetWatchlistUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaMockFactory,
    )

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.application.use_cases import GetWatchlistUseCase
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.shared_kernel.value_objects import CollectionMediaType


@pytest.mark.unit
class TestGetWatchlistUseCase:
    """Tests for getting watchlist items with metadata."""

    @pytest.mark.asyncio
    async def test_should_return_items_with_metadata(self, movie_mock: MediaMockFactory) -> None:
        items = [
            WatchlistItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
            ),
        ]
        movie = movie_mock("mov_abc123def456", "Inception")

        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = items

        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_movie_repo.find_by_ids.return_value = {"mov_abc123def456": movie}

        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(GetWatchlistInput())

        assert len(result) == 1
        assert isinstance(result[0], WatchlistItemOutput)
        assert result[0].title == "Inception"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_items(self) -> None:
        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = []
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(GetWatchlistInput())

        assert result == []

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        items = [
            WatchlistItem.create(
                media_id="mov_missing00000",
                media_type=CollectionMediaType.MOVIE,
            ),
        ]
        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = items

        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_movie_repo.find_by_ids.return_value = {}

        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(GetWatchlistInput())

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_mixed_media_types(
        self, movie_mock: MediaMockFactory, series_mock: MediaMockFactory
    ) -> None:
        items = [
            WatchlistItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
            ),
            WatchlistItem.create(
                media_id="ser_xyz789abc123",
                media_type=CollectionMediaType.SERIES,
            ),
        ]
        movie = movie_mock("mov_abc123def456", "Inception")
        series = series_mock("ser_xyz789abc123", "Breaking Bad")

        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = items

        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_movie_repo.find_by_ids.return_value = {"mov_abc123def456": movie}

        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_series_repo.find_by_ids.return_value = {"ser_xyz789abc123": series}

        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(GetWatchlistInput())

        assert len(result) == 2
        assert result[0].title == "Inception"
        assert result[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_respect_limit(self) -> None:
        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = []
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(GetWatchlistInput(limit=25))

        mock_watchlist_repo.list_all.assert_called_once_with(limit=25)

    @pytest.mark.asyncio
    async def test_should_pass_language_to_get_title(self, movie_mock: MediaMockFactory) -> None:
        items = [
            WatchlistItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
            ),
        ]
        movie = movie_mock("mov_abc123def456")

        mock_watchlist_repo = AsyncMock(spec=WatchlistRepository)
        mock_watchlist_repo.list_all.return_value = items

        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_movie_repo.find_by_ids.return_value = {"mov_abc123def456": movie}

        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = GetWatchlistUseCase(
            watchlist_repository=mock_watchlist_repo,
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(GetWatchlistInput(lang="pt-BR"))

        movie.get_title.assert_called_once_with("pt-BR")
