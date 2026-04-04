"""Tests for GetFileVariantsUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetFileVariantsInput, MediaFileOutput
from src.modules.media.application.use_cases import GetFileVariantsUseCase
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MediaFile, Resolution
from src.shared_kernel.value_objects.file_path import FilePath


@pytest.mark.unit
class TestGetFileVariantsUseCase:
    """Tests for GetFileVariantsUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_all_variants(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception_1080p.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=48_000_000_000,
                resolution=Resolution("4K"),
            ),
        )
        mock_movie_repo.find_by_id.return_value = movie

        use_case = GetFileVariantsUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(
            GetFileVariantsInput(media_id=str(movie.id)),
        )

        assert len(result) == 2
        assert all(isinstance(f, MediaFileOutput) for f in result)

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_missing_movie(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_movie_repo.find_by_id.return_value = None

        use_case = GetFileVariantsUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetFileVariantsInput(media_id="mov_nonexistent1"),
            )

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_invalid_prefix(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = GetFileVariantsUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetFileVariantsInput(media_id="unknown_abc123"),
            )
