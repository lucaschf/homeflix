"""Tests for ListConflictsUseCase (ADR-015 Phase 1)."""

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos.conflict_dtos import ListConflictsInput
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    MovieId,
    Title,
    Year,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from tests.modules.media.unit.conftest import make_media_uow_mock


def _conflict(
    *,
    a_id: str = "mov_aaaaaaaaaaaa",
    b_id: str = "mov_bbbbbbbbbbbb",
    conflict_id: str = "cnf_xxxxxxxxxxxx",
    a_type: str = "movie",
    b_type: str = "movie",
) -> MediaConflict:
    detected = MediaConflict.detect(
        candidate_a_id=a_id,
        candidate_a_type=a_type,
        candidate_a_runtime_minutes=120.0,
        candidate_b_id=b_id,
        candidate_b_type=b_type,
        candidate_b_runtime_minutes=120.0,
        match_reason=MatchReason.TMDB_ID,
    )
    return detected.with_updates(id=MediaConflictId(conflict_id))


def _movie(*, external_id: str, title: str, year: int = 2020) -> Movie:
    return Movie(
        id=MovieId(external_id),
        library_id="lib_test12345678",
        title=Title(title),
        year=Year(year),
        duration=Duration(7200),
    )


class TestListConflictsUseCase:
    @pytest.mark.asyncio
    async def test_empty_repository_returns_no_items(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.list_pending.return_value = PaginatedResult(
            items=[],
            pagination=Pagination(next_cursor=None, has_more=False),
        )

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(ListConflictsInput())

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None
        mocks.movies.find_by_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_hydrates_titles_and_years_for_movie_candidates(self) -> None:
        mocks = make_media_uow_mock()
        conflict = _conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb")
        mocks.media_conflicts.list_pending.return_value = PaginatedResult(
            items=[conflict],
            pagination=Pagination(next_cursor="next-page", has_more=True),
        )
        mocks.movies.find_by_ids.return_value = {
            "mov_aaaaaaaaaaaa": _movie(external_id="mov_aaaaaaaaaaaa", title="Lhs"),
            "mov_bbbbbbbbbbbb": _movie(external_id="mov_bbbbbbbbbbbb", title="Rhs"),
        }

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(ListConflictsInput(cursor="prev", limit=5))

        assert result.has_more is True
        assert result.next_cursor == "next-page"
        assert len(result.items) == 1

        summary = result.items[0]
        assert summary.conflict_id == "cnf_xxxxxxxxxxxx"
        assert summary.candidate_a.title == "Lhs"
        assert summary.candidate_b.title == "Rhs"
        assert summary.candidate_a.year == 2020

        mocks.media_conflicts.list_pending.assert_awaited_once_with(cursor="prev", limit=5)

    @pytest.mark.asyncio
    async def test_missing_movie_surfaces_as_unhydrated_candidate(self) -> None:
        mocks = make_media_uow_mock()
        conflict = _conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb")
        mocks.media_conflicts.list_pending.return_value = PaginatedResult(
            items=[conflict],
            pagination=Pagination(next_cursor=None, has_more=False),
        )
        # Only side A is in the lookup map; side B is "vanished".
        mocks.movies.find_by_ids.return_value = {
            "mov_aaaaaaaaaaaa": _movie(external_id="mov_aaaaaaaaaaaa", title="Lhs"),
        }

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(ListConflictsInput())

        summary = result.items[0]
        assert summary.candidate_a.title == "Lhs"
        assert summary.candidate_b.title is None
        assert summary.candidate_b.year is None

    @pytest.mark.asyncio
    async def test_series_candidate_skips_movie_lookup_for_that_side(self) -> None:
        mocks = make_media_uow_mock()
        conflict = _conflict(
            a_id="mov_aaaaaaaaaaaa",
            b_id="ser_bbbbbbbbbbbb",
            b_type="series",
        )
        mocks.media_conflicts.list_pending.return_value = PaginatedResult(
            items=[conflict],
            pagination=Pagination(next_cursor=None, has_more=False),
        )
        mocks.movies.find_by_ids.return_value = {
            "mov_aaaaaaaaaaaa": _movie(external_id="mov_aaaaaaaaaaaa", title="Lhs"),
        }

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(ListConflictsInput())

        summary = result.items[0]
        assert summary.candidate_a.title == "Lhs"
        # Series support is out-of-scope in Phase 1; the candidate surfaces
        # with ``title=None`` so the admin UI can still render the row.
        assert summary.candidate_b.title is None
        assert summary.candidate_b.media_type == "series"
