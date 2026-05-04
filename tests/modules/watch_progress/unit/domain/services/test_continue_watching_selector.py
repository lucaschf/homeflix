"""Tests for the ContinueWatchingSelector domain service."""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.services import (
    ContinueWatchingSelection,
    ContinueWatchingSelector,
)
from src.modules.watch_progress.domain.value_objects import (
    EpisodeCandidate,
    WatchableMediaType,
    WatchStatus,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _progress(
    media_id: str,
    status: WatchStatus = WatchStatus.IN_PROGRESS,
    last_watched_at: datetime | None = None,
) -> WatchProgress:
    """Build a ``WatchProgress`` with the given status and timestamp."""
    return WatchProgress(
        profile_id=_PROFILE_ID,
        media_id=media_id,
        media_type=WatchableMediaType.EPISODE,
        position_seconds=900,
        duration_seconds=3600,
        status=status,
        last_watched_at=last_watched_at or datetime(2026, 4, 9, tzinfo=UTC),
    )


def _candidate(
    season: int,
    episode: int,
    *,
    progress: WatchProgress | None = None,
    series_id: str = "ser_ABC",
) -> EpisodeCandidate:
    """Build an EpisodeCandidate with derived composite id."""
    media_id = f"epi_{series_id}_{season}_{episode}"
    return EpisodeCandidate(
        series_id=series_id,
        media_id=media_id,
        season_number=season,
        episode_number=episode,
        episode_title=f"Episode {episode}",
        duration_seconds=3600,
        progress=progress,
    )


@pytest.mark.unit
class TestContinueWatchingSelectorEmptyCases:
    def test_empty_candidates_selects_nothing(self) -> None:
        selector = ContinueWatchingSelector()
        result = selector.pick([])
        assert result == ContinueWatchingSelection(candidate=None, latest_watched_at=None)

    def test_candidates_without_progress_select_nothing(self) -> None:
        selector = ContinueWatchingSelector()
        result = selector.pick([_candidate(1, 1), _candidate(1, 2)])
        assert result.candidate is None
        assert result.latest_watched_at is None


@pytest.mark.unit
class TestInProgressPriority:
    def test_single_in_progress_episode_is_selected(self) -> None:
        cand = _candidate(2, 3, progress=_progress("epi_ser_ABC_2_3"))
        result = ContinueWatchingSelector().pick([cand])
        assert result.candidate is cand

    def test_highest_numbered_in_progress_wins_against_earlier_ones(self) -> None:
        early = _candidate(1, 1, progress=_progress("epi_ser_ABC_1_1"))
        mid = _candidate(1, 5, progress=_progress("epi_ser_ABC_1_5"))
        later = _candidate(2, 1, progress=_progress("epi_ser_ABC_2_1"))

        result = ContinueWatchingSelector().pick([early, mid, later])

        assert result.candidate is later

    def test_in_progress_wins_over_completed_even_if_earlier_in_sequence(self) -> None:
        completed = _candidate(
            2,
            5,
            progress=_progress("epi_ser_ABC_2_5", status=WatchStatus.COMPLETED),
        )
        in_progress = _candidate(1, 2, progress=_progress("epi_ser_ABC_1_2"))

        result = ContinueWatchingSelector().pick([in_progress, completed])

        assert result.candidate is in_progress


@pytest.mark.unit
class TestNextUnwatchedFallback:
    def test_first_unwatched_after_last_completed_is_selected(self) -> None:
        s01e01 = _candidate(
            1, 1, progress=_progress("epi_ser_ABC_1_1", status=WatchStatus.COMPLETED)
        )
        s01e02 = _candidate(
            1, 2, progress=_progress("epi_ser_ABC_1_2", status=WatchStatus.COMPLETED)
        )
        s01e03 = _candidate(1, 3)
        s01e04 = _candidate(1, 4)

        result = ContinueWatchingSelector().pick([s01e01, s01e02, s01e03, s01e04])

        assert result.candidate is s01e03

    def test_completed_with_no_unwatched_after_returns_none(self) -> None:
        s01e01 = _candidate(
            1, 1, progress=_progress("epi_ser_ABC_1_1", status=WatchStatus.COMPLETED)
        )
        s01e02 = _candidate(
            1, 2, progress=_progress("epi_ser_ABC_1_2", status=WatchStatus.COMPLETED)
        )

        result = ContinueWatchingSelector().pick([s01e01, s01e02])

        assert result.candidate is None

    def test_unwatched_before_last_completed_is_skipped(self) -> None:
        """Gaps in the "watched" history don't force the user back to them."""
        s01e01 = _candidate(1, 1)  # skipped entirely
        s01e02 = _candidate(
            1, 2, progress=_progress("epi_ser_ABC_1_2", status=WatchStatus.COMPLETED)
        )
        s01e03 = _candidate(1, 3)

        result = ContinueWatchingSelector().pick([s01e01, s01e02, s01e03])

        assert result.candidate is s01e03


@pytest.mark.unit
class TestLatestWatchedAt:
    def test_returns_max_timestamp_across_progress_records(self) -> None:
        older = datetime(2026, 1, 1, tzinfo=UTC)
        newer = older + timedelta(days=5)

        s01e01 = _candidate(
            1,
            1,
            progress=_progress("epi_ser_ABC_1_1", last_watched_at=older),
        )
        s01e02 = _candidate(
            1,
            2,
            progress=_progress("epi_ser_ABC_1_2", last_watched_at=newer),
        )

        result = ContinueWatchingSelector().pick([s01e01, s01e02])

        assert result.latest_watched_at == newer

    def test_returned_even_when_no_candidate_is_selectable(self) -> None:
        """All-completed series still surfaces the latest timestamp."""
        older = datetime(2026, 1, 1, tzinfo=UTC)
        newer = older + timedelta(days=5)

        s01e01 = _candidate(
            1,
            1,
            progress=_progress("epi_ser_ABC_1_1", WatchStatus.COMPLETED, older),
        )
        s01e02 = _candidate(
            1,
            2,
            progress=_progress("epi_ser_ABC_1_2", WatchStatus.COMPLETED, newer),
        )

        result = ContinueWatchingSelector().pick([s01e01, s01e02])

        assert result.candidate is None
        assert result.latest_watched_at == newer
