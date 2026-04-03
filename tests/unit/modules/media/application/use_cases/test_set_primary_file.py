"""Tests for SetPrimaryFileUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import SetPrimaryFileInput
from src.modules.media.application.use_cases import SetPrimaryFileUseCase
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MediaFile, Resolution
from src.shared_kernel.value_objects.file_path import FilePath


def _create_movie_with_variants() -> Movie:
    """Create a movie with multiple file variants."""
    movie = Movie.create(
        title="Inception",
        year=2010,
        duration=8880,
        file_path="/movies/inception_1080p.mkv",
        file_size=4_000_000_000,
        resolution="1080p",
    )
    return movie.with_file(
        MediaFile(
            file_path=FilePath("/movies/inception_4k.mkv"),
            file_size=48_000_000_000,
            resolution=Resolution("4K"),
        ),
    )


@pytest.mark.unit
class TestSetPrimaryFileUseCase:
    """Tests for SetPrimaryFileUseCase."""

    @pytest.mark.asyncio
    async def test_should_switch_primary(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = _create_movie_with_variants()
        mock_movie_repo.find_by_id.return_value = movie
        mock_movie_repo.save.return_value = movie

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(
            SetPrimaryFileInput(
                media_id=str(movie.id),
                file_path="/movies/inception_4k.mkv",
            ),
        )

        # Verify the save was called with updated primary
        saved_movie = mock_movie_repo.save.call_args[0][0]
        primary = next(f for f in saved_movie.files if f.is_primary)
        assert primary.file_path == FilePath("/movies/inception_4k.mkv")

        # Verify return value
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_should_raise_for_missing_file_path(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = _create_movie_with_variants()
        mock_movie_repo.find_by_id.return_value = movie

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id=str(movie.id),
                    file_path="/movies/nonexistent.mkv",
                ),
            )

    @pytest.mark.asyncio
    async def test_should_raise_for_missing_movie(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_movie_repo.find_by_id.return_value = None

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id="mov_nonexistent1",
                    file_path="/movies/test.mkv",
                ),
            )
