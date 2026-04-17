"""Tests for AddFileVariantUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import AddFileVariantInput, MediaFileOutput
from src.modules.media.application.use_cases import AddFileVariantUseCase
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import make_media_uow_mock


@pytest.mark.unit
class TestAddFileVariantUseCase:
    """Tests for AddFileVariantUseCase."""

    @pytest.mark.asyncio
    async def test_should_add_variant_to_movie(self) -> None:
        mocks = make_media_uow_mock()

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception_1080p.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mocks.movies.find_by_id.return_value = movie
        mocks.movies.save.return_value = movie

        use_case = AddFileVariantUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            AddFileVariantInput(
                media_id=str(movie.id),
                file_path="/movies/inception_4k.mkv",
                file_size=48_000_000_000,
                resolution="4K",
            ),
        )

        assert isinstance(result, MediaFileOutput)
        assert result.file_path == "/movies/inception_4k.mkv"
        assert result.resolution == "4K"
        mocks.movies.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_missing_movie(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_id.return_value = None

        use_case = AddFileVariantUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                AddFileVariantInput(
                    media_id="mov_nonexistent1",
                    file_path="/movies/test.mkv",
                    file_size=1000,
                    resolution="1080p",
                ),
            )

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_invalid_prefix(self) -> None:
        mocks = make_media_uow_mock()

        use_case = AddFileVariantUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                AddFileVariantInput(
                    media_id="unknown_abc123xyz",
                    file_path="/movies/test.mkv",
                    file_size=1000,
                    resolution="1080p",
                ),
            )
