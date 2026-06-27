"""Tests for ResolveMediaConflictUseCase (ADR-015 Phase 2)."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.application.dtos.conflict_dtos import ResolveMediaConflictInput
from src.modules.media.application.use_cases.resolve_media_conflict import (
    ResolveMediaConflictUseCase,
)
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.shared_kernel.integration_events import MovieMergedEvent
from tests.modules.media.unit.conftest import make_media_uow_mock

_CONFLICT_ID = "cnf_xxxxxxxxxxxx"
_WINNER = "mov_winnerwinaaa"
_LOSER = "mov_loserloseraa"


def _pending(
    *,
    a_id: str = _WINNER,
    b_id: str = _LOSER,
) -> MediaConflict:
    base = MediaConflict.detect(
        candidate_a_id=a_id,
        candidate_a_type="movie",
        candidate_a_runtime_minutes=120.0,
        candidate_b_id=b_id,
        candidate_b_type="movie",
        candidate_b_runtime_minutes=125.0,
        match_reason=MatchReason.TMDB_ID,
    )
    return base.with_updates(id=MediaConflictId(_CONFLICT_ID))


async def _save_passthrough(conflict: MediaConflict) -> MediaConflict:
    """Mock repository ``save`` that returns the input unchanged (already has id)."""
    return conflict


class TestMarkDistinct:
    @pytest.mark.asyncio
    async def test_stamps_conflict_and_emits_no_event(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.find_by_id.return_value = _pending()
        mocks.media_conflicts.save.side_effect = _save_passthrough

        event_bus = AsyncMock()
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            ResolveMediaConflictInput(conflict_id=_CONFLICT_ID, action="mark_distinct"),
        )

        assert result.action == "mark_distinct"
        assert result.winner_id is None
        assert result.loser_id is None
        assert result.variants_transferred == 0

        mocks.media_conflicts.save.assert_awaited_once()
        saved = mocks.media_conflicts.save.await_args[0][0]
        assert saved.is_marked_distinct is True

        # Cross-BC handlers are MERGE-only — MARK_DISTINCT publishes nothing.
        event_bus.publish.assert_not_awaited()
        mocks.movies.delete.assert_not_called()
        mocks.movies.transfer_file_variants_between_movies.assert_not_called()


class TestMergeReplace:
    @pytest.mark.asyncio
    async def test_deletes_loser_and_emits_merged_event(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.find_by_id.return_value = _pending()
        mocks.media_conflicts.save.side_effect = _save_passthrough
        mocks.movies.delete.return_value = True

        event_bus = AsyncMock()
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            ResolveMediaConflictInput(
                conflict_id=_CONFLICT_ID,
                action="merge_replace",
                winner_id=_WINNER,
            ),
        )

        assert result.winner_id == _WINNER
        assert result.loser_id == _LOSER
        assert result.variants_transferred == 0

        # No variant transfer for MERGE_REPLACE.
        mocks.movies.transfer_file_variants_between_movies.assert_not_called()
        # Loser was soft-deleted (Movie.delete is soft-delete in this repo).
        mocks.movies.delete.assert_awaited_once()
        loser_arg = mocks.movies.delete.await_args[0][0]
        assert str(loser_arg) == _LOSER

        event_bus.publish.assert_awaited_once()
        published = event_bus.publish.await_args[0][0]
        assert isinstance(published, MovieMergedEvent)
        assert published.winner_id.value == _WINNER
        assert published.loser_id.value == _LOSER
        assert published.keep_loser_variants is False


class TestMergeKeepBoth:
    @pytest.mark.asyncio
    async def test_transfers_variants_then_deletes_loser(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.find_by_id.return_value = _pending()
        mocks.media_conflicts.save.side_effect = _save_passthrough
        mocks.movies.transfer_file_variants_between_movies.return_value = 2
        mocks.movies.delete.return_value = True

        event_bus = AsyncMock()
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory, event_bus=event_bus)

        result = await use_case.execute(
            ResolveMediaConflictInput(
                conflict_id=_CONFLICT_ID,
                action="merge_keep_both",
                winner_id=_WINNER,
            ),
        )

        assert result.variants_transferred == 2
        mocks.movies.transfer_file_variants_between_movies.assert_awaited_once()
        transfer_kwargs = mocks.movies.transfer_file_variants_between_movies.await_args.kwargs
        assert str(transfer_kwargs["source_movie_id"]) == _LOSER
        assert str(transfer_kwargs["target_movie_id"]) == _WINNER

        event_bus.publish.assert_awaited_once()
        assert event_bus.publish.await_args[0][0].keep_loser_variants is True


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_unknown_conflict_id_raises_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.media_conflicts.find_by_id.return_value = None
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ResolveMediaConflictInput(conflict_id=_CONFLICT_ID, action="mark_distinct"),
            )

    @pytest.mark.asyncio
    async def test_already_resolved_conflict_raises_409(self) -> None:
        mocks = make_media_uow_mock()
        from src.modules.media.domain.entities.media_conflict import ResolutionAction

        already_resolved = _pending().resolve(ResolutionAction.MARK_DISTINCT)
        mocks.media_conflicts.find_by_id.return_value = already_resolved
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory)

        with pytest.raises(BusinessRuleViolationException):
            await use_case.execute(
                ResolveMediaConflictInput(conflict_id=_CONFLICT_ID, action="mark_distinct"),
            )

    @pytest.mark.asyncio
    async def test_unknown_action_string_raises_validation(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ResolveMediaConflictUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainValidationException):
            await use_case.execute(
                ResolveMediaConflictInput(conflict_id=_CONFLICT_ID, action="not_a_real_action"),
            )
        mocks.factory.assert_not_called()
