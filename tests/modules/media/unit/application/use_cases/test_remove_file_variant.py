"""Tests for RemoveFileVariantUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos import RemoveFileVariantInput
from src.modules.media.application.use_cases import RemoveFileVariantUseCase
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

    @pytest.mark.asyncio
    async def test_should_raise_when_movie_not_found(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_movie_repo.find_by_id.return_value = None

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id="mov_nonexistent1",
                    file_path="/movies/test.mkv",
                ),
            )

        assert exc_info.value.resource_type == "Movie"

    @pytest.mark.asyncio
    async def test_should_raise_for_invalid_media_id_prefix(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id="ssn_invalidprefix",
                    file_path="/series/test.mkv",
                ),
            )

        assert exc_info.value.resource_type == "Media"

    @pytest.mark.asyncio
    async def test_should_raise_when_media_id_has_no_underscore(self):
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id="invalidformat",
                    file_path="/movies/test.mkv",
                ),
            )


def _create_series_with_episode_variants() -> Series:
    """Create a series with one episode that has two file variants."""
    series = Series.create(title="Breaking Bad", start_year=2008)
    assert series.id is not None
    episode = Episode(
        id=EpisodeId.generate(),
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
class TestRemoveFileVariantFromEpisode:
    """Tests for removing a file variant from an episode."""

    @pytest.mark.asyncio
    async def test_should_remove_variant_from_episode(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        series = _create_series_with_episode_variants()
        episode = series.seasons[0].episodes[0]
        mock_series_repo.find_by_episode_id.return_value = series
        mock_series_repo.save.return_value = series

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(
            RemoveFileVariantInput(
                media_id=str(episode.id),
                file_path="/series/bb/s01e01_4k.mkv",
            ),
        )

        saved_series = mock_series_repo.save.call_args[0][0]
        saved_episode = saved_series.seasons[0].episodes[0]
        assert len(saved_episode.files) == 1
        assert saved_episode.files[0].file_path == FilePath("/series/bb/s01e01_1080p.mkv")

    @pytest.mark.asyncio
    async def test_should_promote_best_when_removing_primary_from_episode(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)

        series = _create_series_with_episode_variants()
        episode = series.seasons[0].episodes[0]
        mock_series_repo.find_by_episode_id.return_value = series
        mock_series_repo.save.return_value = series

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        await use_case.execute(
            RemoveFileVariantInput(
                media_id=str(episode.id),
                file_path="/series/bb/s01e01_1080p.mkv",
            ),
        )

        saved_series = mock_series_repo.save.call_args[0][0]
        saved_episode = saved_series.seasons[0].episodes[0]
        assert len(saved_episode.files) == 1
        assert saved_episode.files[0].is_primary is True
        assert saved_episode.files[0].file_path == FilePath("/series/bb/s01e01_4k.mkv")

    @pytest.mark.asyncio
    async def test_should_raise_when_episode_not_found(self) -> None:
        mock_movie_repo = AsyncMock(spec=MovieRepository)
        mock_series_repo = AsyncMock(spec=SeriesRepository)
        mock_series_repo.find_by_episode_id.return_value = None

        use_case = RemoveFileVariantUseCase(
            movie_repository=mock_movie_repo,
            series_repository=mock_series_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveFileVariantInput(
                    media_id=str(EpisodeId.generate()),
                    file_path="/series/test.mkv",
                ),
            )

        assert exc_info.value.resource_type == "Episode"
