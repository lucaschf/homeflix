"""Tests for SearchCatalogUseCase."""


import pytest

from src.modules.media.application.dtos.search_dtos import (
    SearchInput,
    SearchItemOutput,
    SearchOutput,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.domain.entities import Movie, Series
from tests.modules.media.unit.conftest import make_media_uow_mock


def _movie(title: str) -> Movie:
    return Movie.create(
        title=title,
        year=2020,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


def _series(title: str) -> Series:
    return Series.create(title=title, start_year=2020)


@pytest.mark.unit
class TestSearchCatalogUseCase:
    """Cross-type merge and filter behavior."""

    @pytest.mark.asyncio
    async def test_should_merge_results_from_both_repos_by_rank(self) -> None:
        mocks = make_media_uow_mock()
        # Movie rank -5 (better) + series rank -2 (worse)
        mocks.movies.search.return_value = [(_movie("Inception"), -5.0)]
        mocks.series.search.return_value = [(_series("Breaking Bad"), -2.0)]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="test"))

        assert isinstance(result, SearchOutput)
        # Movie has better rank (-5 < -2), so it comes first
        assert [item.title for item in result.items] == ["Inception", "Breaking Bad"]
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_should_skip_series_repo_when_filtered_to_movies(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Avatar"), -3.0)]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="avatar", media_type="movie"))

        mocks.movies.search.assert_awaited_once()
        mocks.series.search.assert_not_awaited()
        assert len(result.items) == 1
        assert result.items[0].type == "movie"

    @pytest.mark.asyncio
    async def test_should_skip_movie_repo_when_filtered_to_series(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.search.return_value = [(_series("Dark"), -4.0)]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="dark", media_type="series"))

        mocks.series.search.assert_awaited_once()
        mocks.movies.search.assert_not_awaited()
        assert len(result.items) == 1
        assert result.items[0].type == "series"

    @pytest.mark.asyncio
    async def test_should_trim_combined_results_to_limit(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [
            (_movie("A"), -5.0),
            (_movie("B"), -4.0),
            (_movie("C"), -3.0),
        ]
        mocks.series.search.return_value = [
            (_series("D"), -2.0),
            (_series("E"), -1.0),
        ]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="test", limit=3))

        assert len(result.items) == 3
        assert result.total == 5  # Total before trimming

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_matches(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = []
        mocks.series.search.return_value = []
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="nonexistent"))

        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_should_forward_filters_to_repos(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = []
        mocks.series.search.return_value = []
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            SearchInput(
                query="test",
                genre="Action",
                year_min=2000,
                year_max=2020,
                limit=10,
            )
        )

        call_kwargs = mocks.movies.search.await_args
        assert call_kwargs.kwargs["genre"] == "Action"
        assert call_kwargs.kwargs["year_min"] == 2000
        assert call_kwargs.kwargs["year_max"] == 2020
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_item_output_carries_required_fields(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Test Movie"), -5.0)]
        mocks.series.search.return_value = [(_series("Test Series"), -3.0)]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="test"))

        for item in result.items:
            assert isinstance(item, SearchItemOutput)
            assert item.id
            assert item.title
            assert item.year == 2020
            assert isinstance(item.genres, list)

    @pytest.mark.asyncio
    async def test_should_tag_items_with_correct_type(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Avatar"), -5.0)]
        mocks.series.search.return_value = [(_series("Dark"), -3.0)]
        use_case = SearchCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(SearchInput(query="test"))

        types = {(item.title, item.type) for item in result.items}
        assert types == {("Avatar", "movie"), ("Dark", "series")}
