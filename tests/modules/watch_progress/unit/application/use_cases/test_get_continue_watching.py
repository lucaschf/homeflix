"""Tests for GetContinueWatchingUseCase - episode enrichment."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
)
from src.modules.watch_progress.application.dtos import ContinueWatchingItem
from src.modules.watch_progress.application.use_cases import GetContinueWatchingUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


def _make_progress(media_id: str, media_type: str = "episode") -> WatchProgress:
    """Create a WatchProgress entity for testing."""
    return WatchProgress(
        media_id=media_id,
        media_type=media_type,
        position_seconds=1800,
        duration_seconds=3600,
        status="in_progress",
        last_watched_at=datetime(2026, 4, 9, tzinfo=UTC),
    )


def _make_series_with_episode(
    series_id: str = "ser_Hy9VjMfILYZe",
) -> Series:
    """Create a Series with one season and one episode for testing."""
    series = Series.create(title="Test Series", start_year=2024)
    # Override the generated ID
    series = series.with_updates(id=SeriesId(series_id))
    season = Season(
        id=SeasonId.generate(),
        series_id=series.id,
        season_number=3,
    )
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series.id,
        season_number=3,
        episode_number=2,
        title=Title("The Episode"),
        duration=Duration(3600),
        files=[
            MediaFile(
                file_path=FilePath("/series/test/s03e02.mkv"),
                file_size=1_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )
    season = season.with_episode(episode)
    series = series.with_season(season)
    return series


@pytest.fixture()
def repos() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Create mock repositories."""
    progress_repo = AsyncMock(spec=WatchProgressRepository)
    movie_repo = AsyncMock(spec=MovieRepository)
    series_repo = AsyncMock(spec=SeriesRepository)
    return progress_repo, movie_repo, series_repo


class TestEnrichEpisode:
    """Tests for episode enrichment in continue watching."""

    @pytest.mark.asyncio
    async def test_enrich_valid_composite_episode(self, repos):
        progress_repo, movie_repo, series_repo = repos
        series = _make_series_with_episode()
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_2")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_2": progress,
        }
        series_repo.find_by_id.return_value = series

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1
        item = result.items[0]
        assert isinstance(item, ContinueWatchingItem)
        assert item.series_id == "ser_Hy9VjMfILYZe"
        assert item.series_title == "Test Series"
        assert item.season_number == 3
        assert item.episode_number == 2
        assert item.title == "The Episode"

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_standard_episode_id(self, repos):
        progress_repo, movie_repo, series_repo = repos
        progress = _make_progress("epi_03ZzYaQ77FaB")
        progress_repo.list_recently_watched.return_value = [progress]

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_series(self, repos):
        progress_repo, movie_repo, series_repo = repos
        progress = _make_progress("epi_ser_NotExists123_1_1")
        progress_repo.list_recently_watched.return_value = [progress]
        series_repo.find_by_id.return_value = None

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_season(self, repos):
        progress_repo, movie_repo, series_repo = repos
        series = _make_series_with_episode()
        # Request season 99 which doesn't exist
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_99_1")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_99_1": progress,
        }
        series_repo.find_by_id.return_value = series

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_episode(self, repos):
        progress_repo, movie_repo, series_repo = repos
        series = _make_series_with_episode()
        # Request episode 99 in season 3 which doesn't exist
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_99")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_99": progress,
        }
        series_repo.find_by_id.return_value = series

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_malformed_media_id(self, repos):
        progress_repo, movie_repo, series_repo = repos
        progress = _make_progress("epi_ser_broken")
        progress_repo.list_recently_watched.return_value = [progress]

        use_case = GetContinueWatchingUseCase(
            progress_repository=progress_repo,
            movie_repository=movie_repo,
            series_repository=series_repo,
        )
        from src.modules.watch_progress.application.dtos import GetContinueWatchingInput

        result = await use_case.execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0
