"""Tests for ListLibrariesUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.library.application.use_cases.list_libraries import ListLibrariesUseCase
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


def _make_media_repos() -> tuple[AsyncMock, AsyncMock]:
    movie_repo = AsyncMock(spec=MovieRepository)
    movie_repo.count_under_paths.return_value = 0
    series_repo = AsyncMock(spec=SeriesRepository)
    series_repo.count_under_paths.return_value = 0
    return movie_repo, series_repo


@pytest.mark.unit
class TestListLibrariesUseCase:
    """Unit tests for listing libraries."""

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_libraries(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_all.return_value = []
        movie_repo, series_repo = _make_media_repos()
        use_case = ListLibrariesUseCase(repo, movie_repo, series_repo)

        result = await use_case.execute()

        assert result == []

    @pytest.mark.asyncio
    async def test_should_return_all_libraries(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_all.return_value = [
            Library.create(name="Movies", library_type="movies", paths=["/m"]),
            Library.create(name="Series", library_type="series", paths=["/s"]),
        ]
        movie_repo, series_repo = _make_media_repos()
        use_case = ListLibrariesUseCase(repo, movie_repo, series_repo)

        result = await use_case.execute()

        assert len(result) == 2
        assert result[0].name == "Movies"
        assert result[1].name == "Series"
