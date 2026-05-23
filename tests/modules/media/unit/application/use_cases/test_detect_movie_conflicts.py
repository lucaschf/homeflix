"""Tests for DetectMovieConflictsUseCase (ADR-015 Phase 1)."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.dtos.conflict_dtos import DetectMovieConflictsInput
from src.modules.media.application.use_cases.detect_movie_conflicts import (
    DetectMovieConflictsUseCase,
)
from src.modules.media.domain.entities import MediaConflict
from src.modules.media.domain.entities.media_conflict import MatchReason
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.events import MediaConflictDetectedEvent
from src.modules.media.domain.value_objects import (
    Duration,
    MovieId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from tests.modules.media.unit.conftest import make_media_uow_mock


def _build_movie(*, external_id: str, duration_seconds: int = 7200) -> Movie:
    return Movie(
        id=MovieId(external_id),
        library_id="lib_test12345678",
        title=Title("Example"),
        year=Year(2020),
        duration=Duration(duration_seconds),
        tmdb_id=TmdbId(27205),
    )


class TestDetectMovieConflictsUseCase:
    @pytest.mark.asyncio
    async def test_no_other_movies_creates_no_conflicts(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl")
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie]

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        assert result.conflict_ids == []
        mocks.media_conflicts.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_collision_creates_conflict_and_publishes_event(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl", duration_seconds=7200)
        other = _build_movie(external_id="mov_mnopqrstuvwx", duration_seconds=7320)
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]
        mocks.media_conflicts.find_pending_by_pair.return_value = None
        mocks.media_conflicts.save.side_effect = _stamp_conflict_id

        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 1
        mocks.media_conflicts.save.assert_called_once()
        saved_conflict = mocks.media_conflicts.save.call_args[0][0]
        assert isinstance(saved_conflict, MediaConflict)
        assert saved_conflict.match_reason is MatchReason.TMDB_ID
        # delta 7320 - 7200 = 120s = 2.0 min
        assert saved_conflict.runtime_delta_minutes == pytest.approx(2.0)

        event_bus.publish.assert_awaited_once()
        published = event_bus.publish.await_args[0][0]
        assert isinstance(published, MediaConflictDetectedEvent)
        assert published.candidate_a_id == "mov_abcdefghijkl"
        assert published.candidate_b_id == "mov_mnopqrstuvwx"

    @pytest.mark.asyncio
    async def test_existing_pending_pair_is_skipped(self) -> None:
        mocks = make_media_uow_mock()
        self_movie = _build_movie(external_id="mov_abcdefghijkl")
        other = _build_movie(external_id="mov_mnopqrstuvwx")
        mocks.movies.find_all_by_tmdb_id.return_value = [self_movie, other]

        existing = MediaConflict.detect(
            candidate_a_id="mov_mnopqrstuvwx",
            candidate_a_type="movie",
            candidate_a_runtime_minutes=120.0,
            candidate_b_id="mov_abcdefghijkl",
            candidate_b_type="movie",
            candidate_b_runtime_minutes=120.0,
            match_reason=MatchReason.TMDB_ID,
        )
        mocks.media_conflicts.find_pending_by_pair.return_value = existing

        event_bus = AsyncMock()
        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.media_conflicts.save.assert_not_called()
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_self_movie_vanishing_returns_empty_result(self) -> None:
        # Defensive: enrichment fired but the source movie was deleted
        # between commit and handler dispatch — the candidate list
        # contains only the *other* movie. Use case should not create
        # a conflict against a non-existent left-hand side.
        mocks = make_media_uow_mock()
        other = _build_movie(external_id="mov_mnopqrstuvwx")
        mocks.movies.find_all_by_tmdb_id.return_value = [other]

        use_case = DetectMovieConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            DetectMovieConflictsInput(media_id="mov_abcdefghijkl", tmdb_id=27205),
        )

        assert result.conflicts_created == 0
        mocks.media_conflicts.save.assert_not_called()


async def _stamp_conflict_id(conflict: MediaConflict) -> MediaConflict:
    """Stand-in for the persistence side of ``save`` — assigns an id."""
    return conflict.with_updates(
        id=MediaConflictId("cnf_stamped12345"),
    )
