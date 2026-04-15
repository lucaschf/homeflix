"""Tests for GetLibraryByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import GetLibraryByIdInput
from src.modules.library.application.use_cases.get_library_by_id import (
    GetLibraryByIdUseCase,
)
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


def _make_media_repos() -> tuple[AsyncMock, AsyncMock]:
    movie_repo = AsyncMock(spec=MovieRepository)
    movie_repo.count_under_paths.return_value = 0
    series_repo = AsyncMock(spec=SeriesRepository)
    series_repo.count_under_paths.return_value = 0
    return movie_repo, series_repo


@pytest.mark.unit
class TestGetLibraryByIdUseCase:
    """Unit tests for fetching a library by id."""

    @pytest.mark.asyncio
    async def test_should_return_library_when_found(self) -> None:
        lib = Library.create(name="Movies", library_type="movies", paths=["/m"])
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_by_id.return_value = lib
        movie_repo, series_repo = _make_media_repos()
        use_case = GetLibraryByIdUseCase(repo, movie_repo, series_repo)

        result = await use_case.execute(
            GetLibraryByIdInput(library_id=str(lib.id)),
        )

        assert result.name == "Movies"

    @pytest.mark.asyncio
    async def test_should_raise_when_not_found(self) -> None:
        repo = AsyncMock(spec=LibraryRepository)
        repo.find_by_id.return_value = None
        movie_repo, series_repo = _make_media_repos()
        use_case = GetLibraryByIdUseCase(repo, movie_repo, series_repo)
        lib_id = str(LibraryId.generate())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetLibraryByIdInput(library_id=lib_id),
            )
