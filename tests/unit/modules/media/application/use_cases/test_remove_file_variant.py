"""Tests for RemoveFileVariantUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos import RemoveFileVariantInput
from src.modules.media.application.use_cases import RemoveFileVariantUseCase
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
class TestRemoveFileVariantUseCase:
    """Tests for RemoveFileVariantUseCase."""

    @pytest.mark.asyncio
    async def test_should_remove_non_primary_variant(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = _create_movie_with_variants()
        mock_movie_repo.find_by_id.return_value = movie
        mock_movie_repo.save.return_value = movie

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(
            RemoveFileVariantInput(
                media_id=str(movie.id),
                file_path="/movies/inception_4k.mkv",
            ),
        )

        mock_movie_repo.save.assert_called_once()
        saved_movie = mock_movie_repo.save.call_args[0][0]
        assert len(saved_movie.files) == 1

    @pytest.mark.asyncio
    async def test_should_promote_best_when_removing_primary(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = _create_movie_with_variants()
        mock_movie_repo.find_by_id.return_value = movie
        mock_movie_repo.save.return_value = movie

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(
            RemoveFileVariantInput(
                media_id=str(movie.id),
                file_path="/movies/inception_1080p.mkv",
            ),
        )

        saved_movie = mock_movie_repo.save.call_args[0][0]
        assert len(saved_movie.files) == 1
        assert saved_movie.files[0].is_primary is True
        assert saved_movie.files[0].file_path == FilePath("/movies/inception_4k.mkv")

    @pytest.mark.asyncio
    async def test_should_raise_when_removing_last_file(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mock_movie_repo.find_by_id.return_value = movie

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(UseCaseValidationException, match="last file variant"):
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id=str(movie.id),
                    file_path="/movies/inception.mkv",
                ),
            )

    @pytest.mark.asyncio
    async def test_should_raise_when_file_path_not_found(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        movie = _create_movie_with_variants()
        mock_movie_repo.find_by_id.return_value = movie

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id=str(movie.id),
                    file_path="/movies/nonexistent.mkv",
                ),
            )
