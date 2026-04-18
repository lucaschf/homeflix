"""Tests for GetContinueWatchingUseCase - episode enrichment and deduplication."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.application.ports import (
    EpisodeInfo,
    MediaLookupPort,
    SeriesWithEpisodesInfo,
)
from src.modules.watch_progress.application.use_cases import GetContinueWatchingUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository
from src.modules.watch_progress.domain.value_objects import WatchableMediaType


def _make_progress(
    media_id: str,
    media_type: WatchableMediaType = WatchableMediaType.EPISODE,
    *,
    status: str = "in_progress",
    position: int = 1800,
    last_watched: datetime | None = None,
) -> WatchProgress:
    """Create a WatchProgress entity for testing."""
    return WatchProgress(
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=3600,
        status=status,
        last_watched_at=last_watched or datetime(2026, 4, 9, tzinfo=UTC),
    )


def _make_series_info(
    series_id: str,
    episodes_per_season: dict[int, list[int]],
    title: str = "Test Series",
) -> SeriesWithEpisodesInfo:
    """Create a ``SeriesWithEpisodesInfo`` with specified seasons/episodes.

    Args:
        series_id: External series ID.
        episodes_per_season: Mapping of season_number to list of episode_numbers.
        title: Series title.
    """
    episodes: list[EpisodeInfo] = []
    for season_num in sorted(episodes_per_season):
        for ep_num in sorted(episodes_per_season[season_num]):
            episodes.append(
                EpisodeInfo(
                    season_number=season_num,
                    episode_number=ep_num,
                    title=f"Episode {ep_num}",
                    duration_seconds=3600,
                )
            )
    return SeriesWithEpisodesInfo(
        series_id=series_id,
        title=title,
        poster_path=None,
        backdrop_path=None,
        episodes=episodes,
    )


@pytest.fixture()
def repos() -> tuple[AsyncMock, AsyncMock]:
    """Create mock progress repository and media lookup port."""
    progress_repo = AsyncMock(spec=WatchProgressRepository)
    media_lookup = AsyncMock(spec=MediaLookupPort)
    return progress_repo, media_lookup


def _make_use_case(
    repos: tuple[AsyncMock, AsyncMock],
) -> GetContinueWatchingUseCase:
    progress_repo, media_lookup = repos
    return GetContinueWatchingUseCase(
        progress_repository=progress_repo,
        media_lookup=media_lookup,
    )


class TestEnrichEpisode:
    """Tests for episode enrichment in continue watching."""

    @pytest.mark.asyncio
    async def test_enrich_valid_composite_episode(self, repos):
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_2")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_2": progress,
        }
        media_lookup.get_series_with_episodes.return_value = series

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1
        item = result.items[0]
        assert isinstance(item, ContinueWatchingItem)
        assert item.series_id == "ser_Hy9VjMfILYZe"
        assert item.series_title == "Test Series"
        assert item.season_number == 3
        assert item.episode_number == 2

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_standard_episode_id(self, repos):
        progress_repo, _ = repos
        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_03ZzYaQ77FaB"),
        ]

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_series(self, repos):
        progress_repo, media_lookup = repos
        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_NotExists123_1_1"),
        ]
        media_lookup.get_series_with_episodes.return_value = None

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_season(self, repos):
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_99_1")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_99_1": progress,
        }
        media_lookup.get_series_with_episodes.return_value = series

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_missing_episode(self, repos):
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_Hy9VjMfILYZe", {3: [2]})
        progress = _make_progress("epi_ser_Hy9VjMfILYZe_3_99")
        progress_repo.list_recently_watched.return_value = [progress]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_Hy9VjMfILYZe_3_99": progress,
        }
        media_lookup.get_series_with_episodes.return_value = series

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_enrich_returns_none_for_malformed_media_id(self, repos):
        progress_repo, _ = repos
        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_broken"),
        ]

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0


class TestSeriesDeduplication:
    """Tests for series deduplication and episode selection."""

    @pytest.mark.asyncio
    async def test_multiple_episodes_same_series_returns_one_item(self, repos):
        """Multiple in-progress episodes from same series → single item."""
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2, 3]})
        media_lookup.get_series_with_episodes.return_value = series

        p1 = _make_progress("epi_ser_AAAAAAAAAAAA_1_1")
        p2 = _make_progress("epi_ser_AAAAAAAAAAAA_1_2")
        p3 = _make_progress("epi_ser_AAAAAAAAAAAA_1_3")
        progress_repo.list_recently_watched.return_value = [p1, p2, p3]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": p1,
            "epi_ser_AAAAAAAAAAAA_1_2": p2,
            "epi_ser_AAAAAAAAAAAA_1_3": p3,
        }

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_picks_highest_in_progress_episode(self, repos):
        """Should pick the highest-numbered in-progress episode."""
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2, 3], 2: [1, 2]})
        media_lookup.get_series_with_episodes.return_value = series

        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_AAAAAAAAAAAA_1_2"),
        ]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_3": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_3",
                status="in_progress",
            ),
            "epi_ser_AAAAAAAAAAAA_2_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_2_1",
                status="in_progress",
            ),
        }

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1
        assert result.items[0].season_number == 2
        assert result.items[0].episode_number == 1

    @pytest.mark.asyncio
    async def test_picks_next_unwatched_when_all_completed(self, repos):
        """Completed episodes + unwatched episodes → next unwatched."""
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2, 3]})
        media_lookup.get_series_with_episodes.return_value = series

        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_AAAAAAAAAAAA_1_1", status="completed"),
        ]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
        }

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1
        assert result.items[0].season_number == 1
        assert result.items[0].episode_number == 3
        assert result.items[0].percentage == 0.0

    @pytest.mark.asyncio
    async def test_returns_nothing_when_all_episodes_completed(self, repos):
        """All episodes completed, none unwatched → no item."""
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2]})
        media_lookup.get_series_with_episodes.return_value = series

        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_AAAAAAAAAAAA_1_1", status="completed"),
        ]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
        }

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_two_series_return_one_item_each(self, repos):
        """Two different series → two items, one per series."""
        progress_repo, media_lookup = repos
        series_a = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2]}, title="Series A")
        series_b = _make_series_info("ser_BBBBBBBBBBBB", {1: [1]}, title="Series B")

        async def get_series_side_effect(sid, lang):
            if sid == "ser_AAAAAAAAAAAA":
                return series_a
            if sid == "ser_BBBBBBBBBBBB":
                return series_b
            return None

        media_lookup.get_series_with_episodes.side_effect = get_series_side_effect

        pa = _make_progress("epi_ser_AAAAAAAAAAAA_1_1")
        pb = _make_progress("epi_ser_BBBBBBBBBBBB_1_1")
        progress_repo.list_recently_watched.return_value = [pa, pb]

        def find_by_media_ids_side_effect(ids):
            result = {}
            if "epi_ser_AAAAAAAAAAAA_1_1" in ids:
                result["epi_ser_AAAAAAAAAAAA_1_1"] = pa
            if "epi_ser_BBBBBBBBBBBB_1_1" in ids:
                result["epi_ser_BBBBBBBBBBBB_1_1"] = pb
            return result

        progress_repo.find_by_media_ids.side_effect = find_by_media_ids_side_effect

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 2
        series_ids = {item.series_id for item in result.items}
        assert series_ids == {"ser_AAAAAAAAAAAA", "ser_BBBBBBBBBBBB"}

    @pytest.mark.asyncio
    async def test_mixed_in_progress_and_completed_across_seasons(self, repos):
        """S1 completed, S2E1 in-progress → picks S2E1."""
        progress_repo, media_lookup = repos
        series = _make_series_info("ser_AAAAAAAAAAAA", {1: [1, 2], 2: [1, 2]})
        media_lookup.get_series_with_episodes.return_value = series

        progress_repo.list_recently_watched.return_value = [
            _make_progress("epi_ser_AAAAAAAAAAAA_2_1"),
        ]
        progress_repo.find_by_media_ids.return_value = {
            "epi_ser_AAAAAAAAAAAA_1_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_1",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_1_2": _make_progress(
                "epi_ser_AAAAAAAAAAAA_1_2",
                status="completed",
            ),
            "epi_ser_AAAAAAAAAAAA_2_1": _make_progress(
                "epi_ser_AAAAAAAAAAAA_2_1",
                status="in_progress",
            ),
        }

        result = await _make_use_case(repos).execute(GetContinueWatchingInput(limit=10))

        assert len(result.items) == 1
        assert result.items[0].season_number == 2
        assert result.items[0].episode_number == 1
