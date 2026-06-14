"""Tests for SearchCatalogUseCase."""


import pytest

from src.modules.media.application.dtos.search_dtos import (
    SearchInput,
    SearchItemOutput,
    SearchOutput,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.domain.entities import Movie, Series
from src.shared_kernel.value_objects import MediaType
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
    make_profile_library_access,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _movie(title: str, *, library_id: str = _LIBRARY_ID) -> Movie:
    return Movie.create(
        library_id=library_id,
        title=title,
        year=2020,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


def _series(title: str, *, library_id: str = _LIBRARY_ID) -> Series:
    return Series.create(library_id=library_id, title=title, start_year=2020)


@pytest.mark.unit
class TestSearchCatalogUseCase:
    """Cross-type merge and filter behavior."""

    @pytest.mark.asyncio
    async def test_should_merge_results_from_both_repos_by_rank(self) -> None:
        mocks = make_media_uow_mock()
        # Movie rank -5 (better) + series rank -2 (worse)
        mocks.movies.search.return_value = [(_movie("Inception"), -5.0)]
        mocks.series.search.return_value = [(_series("Breaking Bad"), -2.0)]
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="test"))

        assert isinstance(result, SearchOutput)
        # Movie has better rank (-5 < -2), so it comes first
        assert [item.title for item in result.items] == ["Inception", "Breaking Bad"]
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_should_skip_series_repo_when_filtered_to_movies(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Avatar"), -3.0)]
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            SearchInput(profile_id=_PROFILE_ID, query="avatar", media_type=MediaType.MOVIE)
        )

        mocks.movies.search.assert_awaited_once()
        mocks.series.search.assert_not_awaited()
        assert len(result.items) == 1
        assert result.items[0].type == "movie"

    @pytest.mark.asyncio
    async def test_should_skip_movie_repo_when_filtered_to_series(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.search.return_value = [(_series("Dark"), -4.0)]
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            SearchInput(profile_id=_PROFILE_ID, query="dark", media_type=MediaType.SERIES)
        )

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
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="test", limit=3))

        assert len(result.items) == 3
        assert result.total == 5  # Total before trimming

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_matches(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = []
        mocks.series.search.return_value = []
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="nonexistent"))

        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_should_forward_filters_to_repos(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = []
        mocks.series.search.return_value = []
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(
            SearchInput(
                profile_id=_PROFILE_ID,
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
        assert list(call_kwargs.kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_search_item_output_carries_required_fields(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Test Movie"), -5.0)]
        mocks.series.search.return_value = [(_series("Test Series"), -3.0)]
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="test"))

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
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="test"))

        types = {(item.title, item.type) for item in result.items}
        assert types == {("Avatar", "movie"), ("Dark", "series")}

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="anything"))

        assert result.items == []
        assert result.total == 0
        mocks.factory.assert_not_called()
        mocks.movies.search.assert_not_awaited()
        mocks.series.search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.search.return_value = [(_movie("Visible"), -5.0)]
        mocks.series.search.return_value = []
        use_case = SearchCatalogUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(SearchInput(profile_id=_PROFILE_ID, query="visible"))

        assert [item.title for item in result.items] == ["Visible"]
        movie_kwargs = mocks.movies.search.await_args.kwargs
        series_kwargs = mocks.series.search.await_args.kwargs
        assert list(movie_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(series_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(movie_kwargs["allowed_library_ids"])
