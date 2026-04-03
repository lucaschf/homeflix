"""Tests for AddFileVariantUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import AddFileVariantInput, MediaFileOutput
from src.modules.media.application.use_cases import AddFileVariantUseCase
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


@pytest.mark.unit
class TestAddFileVariantUseCase:
    """Tests for AddFileVariantUseCase."""

    @pytest.mark.asyncio
    async def test_should_add_variant_to_movie(self):
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
        mock_movie_repo.find_by_id.return_value = movie
        mock_movie_repo.save.return_value = movie

        use_case = AddFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

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
        mock_movie_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_missing_movie(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_movie_repo.find_by_id.return_value = None

        use_case = AddFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

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
    async def test_should_raise_not_found_for_invalid_prefix(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = AddFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                AddFileVariantInput(
                    media_id="unknown_abc123xyz",
                    file_path="/movies/test.mkv",
                    file_size=1000,
                    resolution="1080p",
                ),
            )
