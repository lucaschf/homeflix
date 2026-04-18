"""Tests for DeleteMovieUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import DeleteMovieInput
from src.modules.media.application.use_cases import DeleteMovieUseCase
from tests.modules.media.unit.conftest import make_media_uow_mock


class TestDeleteMovieUseCase:
    """Tests for DeleteMovieUseCase."""

    @pytest.mark.asyncio
    async def test_should_delete_movie_when_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.delete.return_value = True
        use_case = DeleteMovieUseCase(uow_factory=mocks.factory)

        await use_case.execute(DeleteMovieInput(movie_id="mov_abc123def456"))

        mocks.movies.delete.assert_called_once()
        mocks.factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_movie_missing(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.delete.return_value = False
        use_case = DeleteMovieUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(DeleteMovieInput(movie_id="mov_nonexistent1"))

        assert exc_info.value.resource_type == "Movie"
        assert exc_info.value.resource_id == "mov_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_correct_movie_id(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.delete.return_value = True
        use_case = DeleteMovieUseCase(uow_factory=mocks.factory)

        await use_case.execute(DeleteMovieInput(movie_id="mov_abc123def456"))

        call_arg = mocks.movies.delete.call_args[0][0]
        assert str(call_arg) == "mov_abc123def456"
