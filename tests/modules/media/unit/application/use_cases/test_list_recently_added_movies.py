"""Tests for ListRecentlyAddedMoviesUseCase."""

import pytest

from src.modules.media.application.dtos import (
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.use_cases import ListRecentlyAddedMoviesUseCase
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import make_media_uow_mock


def _make_movie(title: str = "Test Movie", year: int = 2020) -> Movie:
    return Movie.create(
        title=title,
        year=year,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


class TestListRecentlyAddedMoviesUseCase:
    """Tests for ListRecentlyAddedMoviesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_summaries_in_repository_order(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [
            _make_movie("Newest"),
            _make_movie("Older"),
        ]
        use_case = ListRecentlyAddedMoviesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedMoviesInput(limit=10))

        assert isinstance(result, ListRecentlyAddedMoviesOutput)
        assert [m.title for m in result.movies] == ["Newest", "Older"]
        assert all(isinstance(m, MovieSummaryOutput) for m in result.movies)

    @pytest.mark.asyncio
    async def test_should_pass_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListRecentlyAddedMoviesInput(limit=15))

        mocks.movies.list_recently_added.assert_awaited_once_with(15)

    @pytest.mark.asyncio
    async def test_should_default_limit_to_twenty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListRecentlyAddedMoviesInput())

        mocks.movies.list_recently_added.assert_awaited_once_with(20)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_repository_empty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedMoviesInput())

        assert result.movies == []

    @pytest.mark.asyncio
    async def test_should_localize_summaries_with_input_lang(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [_make_movie("A Movie", 2024)]
        use_case = ListRecentlyAddedMoviesUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedMoviesInput(lang="pt-BR"))

        assert len(result.movies) == 1
        assert result.movies[0].title == "A Movie"
