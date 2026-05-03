"""Tests for ListRecentlyAddedSeriesUseCase."""

import pytest

from src.modules.media.application.dtos import (
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.application.use_cases import ListRecentlyAddedSeriesUseCase
from src.modules.media.domain.entities import Series
from tests.modules.media.unit.conftest import make_media_uow_mock


def _make_series(title: str = "Test Series", year: int = 2020) -> Series:
    return Series.create(title=title, start_year=year)


class TestListRecentlyAddedSeriesUseCase:
    """Tests for ListRecentlyAddedSeriesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_summaries_in_repository_order(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = [
            _make_series("Newest"),
            _make_series("Older"),
        ]
        use_case = ListRecentlyAddedSeriesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedSeriesInput(limit=10))

        assert isinstance(result, ListRecentlyAddedSeriesOutput)
        assert [s.title for s in result.series] == ["Newest", "Older"]
        assert all(isinstance(s, SeriesSummaryOutput) for s in result.series)

    @pytest.mark.asyncio
    async def test_should_pass_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListRecentlyAddedSeriesInput(limit=15))

        mocks.series.list_recently_added.assert_awaited_once_with(15)

    @pytest.mark.asyncio
    async def test_should_default_limit_to_twenty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListRecentlyAddedSeriesInput())

        mocks.series.list_recently_added.assert_awaited_once_with(20)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_repository_empty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedSeriesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedSeriesInput())

        assert result.series == []
