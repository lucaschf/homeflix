"""Tests for SweepMovieConflictsUseCase (ADR-015 Phase 6.5)."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.dtos.conflict_dtos import (
    DetectMovieConflictsInput,
    DetectMovieConflictsOutput,
)
from src.modules.media.application.use_cases.sweep_movie_conflicts import (
    SweepMovieConflictsUseCase,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    MovieId,
    Title,
    TmdbId,
    Year,
)
from tests.modules.media.unit.conftest import make_media_uow_mock


def _movie(*, external_id: str, tmdb_id: int | None) -> Movie:
    return Movie(
        id=MovieId(external_id),
        library_id="lib_test12345678",
        title=Title("Example"),
        year=Year(2020),
        duration=Duration(7200),
        files=[],
        tmdb_id=None if tmdb_id is None else TmdbId(tmdb_id),
    )


class TestSweepMovieConflictsUseCase:
    @pytest.mark.asyncio
    async def test_invokes_detect_per_movie_with_each_tmdb_id(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_all.return_value = [
            _movie(external_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
            _movie(external_id="mov_bbbbbbbbbbbb", tmdb_id=None),
        ]
        detect = AsyncMock()
        detect.execute.return_value = DetectMovieConflictsOutput(
            conflicts_created=0,
            conflict_ids=[],
        )

        use_case = SweepMovieConflictsUseCase(
            uow_factory=mocks.factory,
            detect_use_case=detect,
        )
        result = await use_case.execute()

        assert result.movies_scanned == 2
        assert result.conflicts_created == 0
        assert detect.execute.await_count == 2
        first_call = detect.execute.await_args_list[0].args[0]
        second_call = detect.execute.await_args_list[1].args[0]
        assert isinstance(first_call, DetectMovieConflictsInput)
        assert first_call.media_id == "mov_aaaaaaaaaaaa"
        assert first_call.tmdb_id == 27205
        assert second_call.media_id == "mov_bbbbbbbbbbbb"
        assert second_call.tmdb_id is None

    @pytest.mark.asyncio
    async def test_aggregates_created_conflict_ids_across_movies(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_all.return_value = [
            _movie(external_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
            _movie(external_id="mov_bbbbbbbbbbbb", tmdb_id=27205),
        ]
        detect = AsyncMock()
        detect.execute.side_effect = [
            DetectMovieConflictsOutput(conflicts_created=1, conflict_ids=["cnf_one12345678"]),
            DetectMovieConflictsOutput(
                conflicts_created=2, conflict_ids=["cnf_two12345678", "cnf_three1234"]
            ),
        ]

        use_case = SweepMovieConflictsUseCase(
            uow_factory=mocks.factory,
            detect_use_case=detect,
        )
        result = await use_case.execute()

        assert result.movies_scanned == 2
        assert result.conflicts_created == 3
        assert result.conflict_ids == [
            "cnf_one12345678",
            "cnf_two12345678",
            "cnf_three1234",
        ]

    @pytest.mark.asyncio
    async def test_continues_after_per_movie_detector_exception(self) -> None:
        # One bad row must not abort the whole sweep.
        mocks = make_media_uow_mock()
        mocks.movies.list_all.return_value = [
            _movie(external_id="mov_aaaaaaaaaaaa", tmdb_id=27205),
            _movie(external_id="mov_bbbbbbbbbbbb", tmdb_id=42),
        ]
        detect = AsyncMock()
        detect.execute.side_effect = [
            RuntimeError("boom"),
            DetectMovieConflictsOutput(
                conflicts_created=1,
                conflict_ids=["cnf_ok1234567890"],
            ),
        ]

        use_case = SweepMovieConflictsUseCase(
            uow_factory=mocks.factory,
            detect_use_case=detect,
        )
        result = await use_case.execute()

        assert result.movies_scanned == 2
        assert result.conflicts_created == 1
        assert result.conflict_ids == ["cnf_ok1234567890"]

    @pytest.mark.asyncio
    async def test_empty_catalog_returns_zero_counters(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_all.return_value = []
        detect = AsyncMock()

        use_case = SweepMovieConflictsUseCase(
            uow_factory=mocks.factory,
            detect_use_case=detect,
        )
        result = await use_case.execute()

        assert result.movies_scanned == 0
        assert result.conflicts_created == 0
        assert result.conflict_ids == []
        detect.execute.assert_not_called()
