"""Tests for ListSeriesUseCase."""

import pytest
from unittest.mock import AsyncMock

from src.application.media.dtos import ListSeriesInput, ListSeriesOutput, SeriesSummaryOutput
from src.application.media.use_cases import ListSeriesUseCase
from src.domain.media.entities import Series
from src.domain.media.repositories import SeriesRepository


class TestListSeriesUseCase:
    """Tests for ListSeriesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_all_series(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series_list = [
            Series.create(title="Show 1", start_year=2020),
            Series.create(title="Show 2", start_year=2021),
        ]
        mock_repo.list_all.return_value = series_list
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert isinstance(result, ListSeriesOutput)
        assert len(result.series) == 2
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_should_return_series_summaries(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
            end_year=2013,
            genres=["Drama", "Crime"],
        )
        mock_repo.list_all.return_value = [series]
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        summary = result.series[0]
        assert isinstance(summary, SeriesSummaryOutput)
        assert summary.title == "Breaking Bad"
        assert summary.start_year == 2008
        assert summary.end_year == 2013
        assert summary.is_ongoing is False
        assert summary.genres == ["Drama", "Crime"]

    @pytest.mark.asyncio
    async def test_should_respect_limit_parameter(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series_list = [
            Series.create(title=f"Show {i}", start_year=2020)
            for i in range(5)
        ]
        mock_repo.list_all.return_value = series_list
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput(limit=2))

        assert len(result.series) == 2
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_series(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_all.return_value = []
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series == []
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_should_indicate_ongoing_series(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Ongoing Show",
            start_year=2020,
        )
        mock_repo.list_all.return_value = [series]
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series[0].is_ongoing is True
        assert result.series[0].end_year is None

    @pytest.mark.asyncio
    async def test_should_include_season_and_episode_counts(self):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Test Show",
            start_year=2020,
        )
        mock_repo.list_all.return_value = [series]
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series[0].season_count == 0
        assert result.series[0].total_episodes == 0
