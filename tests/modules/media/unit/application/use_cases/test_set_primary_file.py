"""Tests for SetPrimaryFileUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import SetPrimaryFileInput
from src.modules.media.application.use_cases import SetPrimaryFileUseCase
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    MediaFile,
    Resolution,
    Title,
)
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


def _create_series_with_episode_variants() -> Series:
    """Create a series with one episode that has multiple file variants."""
    series = Series.create(title="Breaking Bad", start_year=2008)
    assert series.id is not None
    episode_id = EpisodeId.generate()
    episode = Episode(
        id=episode_id,
        series_id=series.id,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(2820),
        files=[
            MediaFile(
                file_path=FilePath("/series/bb/s01e01_1080p.mkv"),
                file_size=2_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
            MediaFile(
                file_path=FilePath("/series/bb/s01e01_4k.mkv"),
                file_size=8_000_000_000,
                resolution=Resolution("4K"),
                is_primary=False,
            ),
        ],
    )
    season = Season(series_id=series.id, season_number=1)
    season = season.with_episode(episode)
    return series.with_season(season)


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

    @pytest.mark.asyncio
    async def test_should_raise_for_invalid_media_id_prefix(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id="ssn_invalidprefix",
                    file_path="/series/test.mkv",
                ),
            )

        assert exc_info.value.resource_type == "Media"

    @pytest.mark.asyncio
    async def test_should_raise_when_media_id_has_no_underscore(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id="invalidformat",
                    file_path="/movies/test.mkv",
                ),
            )


@pytest.mark.unit
class TestSetPrimaryFileForEpisode:
    """Tests for setting primary file on episode variants."""

    @pytest.mark.asyncio
    async def test_should_switch_primary_for_episode(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        series = _create_series_with_episode_variants()
        episode = series.seasons[0].episodes[0]
        mock_series_repo.find_by_episode_id.return_value = series
        mock_series_repo.save.return_value = series

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        result = await use_case.execute(
            SetPrimaryFileInput(
                media_id=str(episode.id),
                file_path="/series/bb/s01e01_4k.mkv",
            ),
        )

        # Verify save was called with the updated series
        saved_series = mock_series_repo.save.call_args[0][0]
        saved_episode = saved_series.seasons[0].episodes[0]
        primary = next(f for f in saved_episode.files if f.is_primary)
        assert primary.file_path == FilePath("/series/bb/s01e01_4k.mkv")

        # Verify return value contains the updated files
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_should_raise_when_episode_not_found(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_series_repo.find_by_episode_id.return_value = None

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id=str(EpisodeId.generate()),
                    file_path="/series/test.mkv",
                ),
            )

        assert exc_info.value.resource_type == "Episode"

    @pytest.mark.asyncio
    async def test_should_raise_when_episode_file_path_missing(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        series = _create_series_with_episode_variants()
        episode = series.seasons[0].episodes[0]
        mock_series_repo.find_by_episode_id.return_value = series

        use_case = SetPrimaryFileUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                SetPrimaryFileInput(
                    media_id=str(episode.id),
                    file_path="/series/bb/nonexistent.mkv",
                ),
            )

        assert exc_info.value.resource_type == "FileVariant"
