"""Tests for ListConflictsUseCase (ADR-015 Phase 1)."""

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.application.dtos.conflict_dtos import ListConflictsInput
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
    ResolutionSource,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    VideoCodec,
    Year,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.shared_kernel.value_objects.file_path import FilePath
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


def _movie(
    *,
    external_id: str,
    title: str,
    year: int = 2020,
    files: list[MediaFile] | None = None,
) -> Movie:
    return Movie(
        id=MovieId(external_id),
        library_id="lib_test12345678",
        title=Title(title),
        year=Year(year),
        duration=Duration(7200),
        files=files or [],
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
    async def test_projects_file_variants_for_movie_candidates(self) -> None:
        mocks = make_media_uow_mock()
        conflict = _conflict(a_id="mov_aaaaaaaaaaaa", b_id="mov_bbbbbbbbbbbb")
        mocks.media_conflicts.list_pending.return_value = PaginatedResult(
            items=[conflict],
            pagination=Pagination(next_cursor=None, has_more=False),
        )
        mocks.movies.find_by_ids.return_value = {
            "mov_aaaaaaaaaaaa": _movie(
                external_id="mov_aaaaaaaaaaaa",
                title="Lhs",
                files=[
                    MediaFile(
                        file_path=FilePath("/movies/lhs_1080p.mkv"),
                        file_size=4_000_000_000,
                        resolution=Resolution("1080p"),
                        video_codec=VideoCodec.H265,
                        is_primary=True,
                    ),
                ],
            ),
            "mov_bbbbbbbbbbbb": _movie(external_id="mov_bbbbbbbbbbbb", title="Rhs"),
        }

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(ListConflictsInput())

        summary = result.items[0]
        assert len(summary.candidate_a.files) == 1
        file = summary.candidate_a.files[0]
        assert file.file_path == "/movies/lhs_1080p.mkv"
        assert file.resolution == "1080p"
        assert file.file_size == 4_000_000_000
        assert file.video_codec == "h265"
        assert file.hdr_format is None
        assert file.is_primary is True
        # A movie with no variants surfaces an empty list, not None.
        assert summary.candidate_b.files == []

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


class TestListResolvedConflicts:
    """ADR-015 Phase 3 — audit view + source filters."""

    @pytest.mark.asyncio
    async def test_state_resolved_calls_list_resolved(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.list_resolved.return_value = PaginatedResult(
            items=[],
            pagination=Pagination(next_cursor=None, has_more=False),
        )

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        await use_case.execute(ListConflictsInput(state="resolved"))

        mocks.media_conflicts.list_resolved.assert_awaited_once_with(
            source=None,
            cursor=None,
            limit=20,
        )
        mocks.media_conflicts.list_pending.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_resolved_with_source_auto_forwards_filter(self) -> None:
        mocks = make_media_uow_mock()
        resolved_auto = _conflict().with_updates(
            resolved_at=__import__("datetime").datetime.now(),
            resolution=ResolutionAction.MERGE_REPLACE,
            winner_id="mov_aaaaaaaaaaaa",
            resolution_source=ResolutionSource.AUTO,
        )
        mocks.media_conflicts.list_resolved.return_value = PaginatedResult(
            items=[resolved_auto],
            pagination=Pagination(next_cursor=None, has_more=False),
        )
        mocks.movies.find_by_ids.return_value = {}

        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            ListConflictsInput(state="resolved", source="auto"),
        )

        mocks.media_conflicts.list_resolved.assert_awaited_once_with(
            source=ResolutionSource.AUTO,
            cursor=None,
            limit=20,
        )
        summary = result.items[0]
        assert summary.resolution == "merge_replace"
        assert summary.resolution_source == "auto"
        assert summary.winner_id == "mov_aaaaaaaaaaaa"

    @pytest.mark.asyncio
    async def test_invalid_state_raises_validation(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        with pytest.raises(DomainValidationException):
            await use_case.execute(ListConflictsInput(state="frozen"))

    @pytest.mark.asyncio
    async def test_source_filter_with_pending_state_raises_validation(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        with pytest.raises(DomainValidationException):
            await use_case.execute(ListConflictsInput(state="pending", source="auto"))

    @pytest.mark.asyncio
    async def test_invalid_source_raises_validation(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListConflictsUseCase(uow_factory=mocks.factory)
        with pytest.raises(DomainValidationException):
            await use_case.execute(ListConflictsInput(state="resolved", source="bogus"))
