"""Tests for ListSeriesUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos import (
    ListSeriesInput,
    ListSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.application.use_cases import ListSeriesUseCase
from src.modules.media.domain.entities import Series
from src.modules.media.domain.repositories import SeriesRepository


def _page(
    series_list: list[Series],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
    total_count: int | None = None,
) -> PaginatedResult[Series]:
    return PaginatedResult(
        items=series_list,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=total_count,
    )


class TestListSeriesUseCase:
    """Tests for ListSeriesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_first_page(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_paginated.return_value = _page(
            [
                Series.create(title="Show 1", start_year=2020),
                Series.create(title="Show 2", start_year=2021),
            ]
        )
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert isinstance(result, ListSeriesOutput)
        assert len(result.series) == 2
        assert result.has_more is False
        assert result.next_cursor is None
        assert result.total_count is None
        mock_repo.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=False,
        )

    @pytest.mark.asyncio
    async def test_should_convert_series_to_summaries(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
            end_year=2013,
            genres=["Drama", "Crime"],
        )
        mock_repo.list_paginated.return_value = _page([series])
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
    async def test_should_pass_cursor_and_limit_to_repository(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_paginated.return_value = _page([])
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        await use_case.execute(ListSeriesInput(cursor="abc123", limit=15))

        mock_repo.list_paginated.assert_awaited_once_with(
            cursor="abc123",
            limit=15,
            include_total=False,
        )

    @pytest.mark.asyncio
    async def test_should_propagate_next_cursor_and_has_more(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_paginated.return_value = _page(
            [Series.create(title="Show 1", start_year=2020)],
            next_cursor="next-token",
            has_more=True,
        )
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.next_cursor == "next-token"
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_empty_page_when_no_series(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_paginated.return_value = _page([])
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_indicate_ongoing_series(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(title="Ongoing Show", start_year=2020)
        mock_repo.list_paginated.return_value = _page([series])
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series[0].is_ongoing is True
        assert result.series[0].end_year is None

    @pytest.mark.asyncio
    async def test_should_include_season_and_episode_counts(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(title="Test Show", start_year=2020)
        mock_repo.list_paginated.return_value = _page([series])
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput())

        assert result.series[0].season_count == 0
        assert result.series[0].total_episodes == 0

    @pytest.mark.asyncio
    async def test_should_request_total_when_include_total_is_true(self) -> None:
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.list_paginated.return_value = _page(
            [Series.create(title="Show 1", start_year=2020)],
            total_count=10,
        )
        use_case = ListSeriesUseCase(series_repository=mock_repo)

        result = await use_case.execute(ListSeriesInput(include_total=True))

        assert result.total_count == 10
        mock_repo.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=True,
        )
