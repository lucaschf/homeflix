"""Tests for GetSeriesByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetSeriesByIdInput, SeriesOutput
from src.modules.media.application.use_cases import GetSeriesByIdUseCase
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeasonId,
    Title,
)
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


@pytest.fixture()
def mock_progress_repo() -> AsyncMock:
    """Create a mock WatchProgressRepository with empty results."""
    repo = AsyncMock(spec=WatchProgressRepository)
    repo.find_by_media_ids.return_value = {}
    return repo


class TestGetSeriesByIdUseCase:
    """Tests for GetSeriesByIdUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_series_when_found(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
        )
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert isinstance(result, SeriesOutput)
        assert result.title == "Breaking Bad"
        assert result.start_year == 2008
        assert result.is_ongoing is True

    @pytest.mark.asyncio
    async def test_should_return_series_with_seasons(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
            end_year=2013,
        )
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )
        series = series.with_season(season)
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.season_count == 1
        assert len(result.seasons) == 1
        assert result.seasons[0].season_number == 1

    @pytest.mark.asyncio
    async def test_should_return_series_with_episodes(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
        )
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )
        episode = Episode(
            id=EpisodeId.generate(),
            series_id=series.id,
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(3600),
            files=[
                MediaFile(
                    file_path=FilePath("/series/bb/s01e01.mkv"),
                    file_size=1_500_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )
        season = season.with_episode(episode)
        series = series.with_season(season)
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.total_episodes == 1
        assert len(result.seasons[0].episodes) == 1
        episode_output = result.seasons[0].episodes[0]
        assert episode_output.title == "Pilot"
        assert episode_output.episode_number == 1
        assert episode_output.duration_formatted == "01:00:00"

    @pytest.mark.asyncio
    async def test_should_return_ongoing_status(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Ongoing Show",
            start_year=2020,
        )
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.is_ongoing is True
        assert result.end_year is None

    @pytest.mark.asyncio
    async def test_should_return_completed_status(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Completed Show",
            start_year=2010,
            end_year=2015,
        )
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.is_ongoing is False
        assert result.end_year == 2015

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_series_missing(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        mock_repo.find_by_id.return_value = None
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(GetSeriesByIdInput(series_id="ser_nonexistent1"))

        assert exc_info.value.resource_type == "Series"
        assert exc_info.value.resource_id == "ser_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_handle_series_with_no_seasons(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="New Show",
            start_year=2024,
        )
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.season_count == 0
        assert result.total_episodes == 0
        assert result.seasons == []

    @pytest.mark.asyncio
    async def test_should_return_genres_as_strings(self, mock_progress_repo):
        mock_repo = AsyncMock(spec=SeriesRepository)
        series = Series.create(
            title="Drama Show",
            start_year=2020,
            genres=["Drama", "Thriller"],
        )
        mock_repo.find_by_id.return_value = series
        use_case = GetSeriesByIdUseCase(
            series_repository=mock_repo,
            progress_repository=mock_progress_repo,
        )

        result = await use_case.execute(GetSeriesByIdInput(series_id=str(series.id)))

        assert result.genres == ["Drama", "Thriller"]
