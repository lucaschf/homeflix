"""Tests for BulkMarkDistinctConflictsUseCase (ADR-015 Phase 4)."""

import pytest

from src.modules.media.application.dtos.conflict_dtos import BulkMarkDistinctInput
from src.modules.media.application.use_cases.bulk_mark_distinct_conflicts import (
    BulkMarkDistinctConflictsUseCase,
)
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
)
from src.modules.media.domain.value_objects import ConflictCandidate
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from tests.modules.media.unit.conftest import make_media_uow_mock


def _pending(conflict_id: str) -> MediaConflict:
    detected = MediaConflict.detect(
        candidate_a=ConflictCandidate(id="mov_aaaaaaaaaaaa", type="movie"),
        candidate_a_runtime_minutes=120.0,
        candidate_b=ConflictCandidate(id="mov_bbbbbbbbbbbb", type="movie"),
        candidate_b_runtime_minutes=120.0,
        match_reason=MatchReason.TMDB_ID,
    )
    return detected.with_updates(id=MediaConflictId(conflict_id))


def _resolved(conflict_id: str) -> MediaConflict:
    return _pending(conflict_id).resolve(ResolutionAction.MARK_DISTINCT)


def _save_returns_input(conflict: MediaConflict) -> MediaConflict:
    return conflict


class TestBulkMarkDistinctConflictsUseCase:
    @pytest.mark.asyncio
    async def test_resolves_all_pending_ids(self) -> None:
        mocks = make_media_uow_mock()
        rows = {
            "cnf_aaaaaaaaaaaa": _pending("cnf_aaaaaaaaaaaa"),
            "cnf_bbbbbbbbbbbb": _pending("cnf_bbbbbbbbbbbb"),
        }
        mocks.media_conflicts.find_by_id.side_effect = lambda cid: rows[str(cid)]
        mocks.media_conflicts.save.side_effect = _save_returns_input

        use_case = BulkMarkDistinctConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            BulkMarkDistinctInput(
                conflict_ids=["cnf_aaaaaaaaaaaa", "cnf_bbbbbbbbbbbb"],
            ),
        )

        assert result.requested == 2
        assert sorted(result.resolved_ids) == ["cnf_aaaaaaaaaaaa", "cnf_bbbbbbbbbbbb"]
        assert result.skipped == []
        # Every saved conflict carries the MARK_DISTINCT resolution.
        for call in mocks.media_conflicts.save.call_args_list:
            assert call[0][0].resolution is ResolutionAction.MARK_DISTINCT

    @pytest.mark.asyncio
    async def test_skips_not_found_and_already_resolved(self) -> None:
        mocks = make_media_uow_mock()
        rows: dict[str, MediaConflict | None] = {
            "cnf_aaaaaaaaaaaa": _pending("cnf_aaaaaaaaaaaa"),
            "cnf_bbbbbbbbbbbb": _resolved("cnf_bbbbbbbbbbbb"),
            "cnf_cccccccccccc": None,
        }
        mocks.media_conflicts.find_by_id.side_effect = lambda cid: rows[str(cid)]
        mocks.media_conflicts.save.side_effect = _save_returns_input

        use_case = BulkMarkDistinctConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            BulkMarkDistinctInput(
                conflict_ids=[
                    "cnf_aaaaaaaaaaaa",
                    "cnf_bbbbbbbbbbbb",
                    "cnf_cccccccccccc",
                ],
            ),
        )

        assert result.resolved_ids == ["cnf_aaaaaaaaaaaa"]
        skipped = {s.conflict_id: s.reason for s in result.skipped}
        assert skipped == {
            "cnf_bbbbbbbbbbbb": "already_resolved",
            "cnf_cccccccccccc": "not_found",
        }
        mocks.media_conflicts.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_id_is_skipped_without_repo_lookup(self) -> None:
        mocks = make_media_uow_mock()
        use_case = BulkMarkDistinctConflictsUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            BulkMarkDistinctInput(conflict_ids=["not-a-conflict-id"]),
        )

        assert result.resolved_ids == []
        assert result.skipped[0].reason == "invalid_id"
        mocks.media_conflicts.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_ids_are_deduped(self) -> None:
        mocks = make_media_uow_mock()
        pending = _pending("cnf_aaaaaaaaaaaa")
        mocks.media_conflicts.find_by_id.return_value = pending
        mocks.media_conflicts.save.side_effect = _save_returns_input

        use_case = BulkMarkDistinctConflictsUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            BulkMarkDistinctInput(
                conflict_ids=["cnf_aaaaaaaaaaaa", "cnf_aaaaaaaaaaaa"],
            ),
        )

        assert result.requested == 1
        assert result.resolved_ids == ["cnf_aaaaaaaaaaaa"]
        mocks.media_conflicts.save.assert_called_once()
