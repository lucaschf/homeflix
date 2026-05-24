"""Tests for the MediaConflict aggregate (ADR-015 Phase 1)."""

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
    ResolutionSource,
    SuggestedAction,
)

_A = "mov_aaaaaaaaaaaa"
_B = "mov_bbbbbbbbbbbb"


def _detect(
    *,
    runtime_a: float | None = 120.0,
    runtime_b: float | None = 120.0,
    match_reason: MatchReason = MatchReason.TMDB_ID,
) -> MediaConflict:
    return MediaConflict.detect(
        candidate_a_id=_A,
        candidate_a_type="movie",
        candidate_a_runtime_minutes=runtime_a,
        candidate_b_id=_B,
        candidate_b_type="movie",
        candidate_b_runtime_minutes=runtime_b,
        match_reason=match_reason,
    )


class TestDetect:
    """``MediaConflict.detect`` factory."""

    def test_identical_runtimes_suggests_likely_same_release(self) -> None:
        conflict = _detect(runtime_a=120.0, runtime_b=120.0)
        assert conflict.runtime_delta_minutes == 0.0
        assert conflict.suggested_action is SuggestedAction.LIKELY_SAME_RELEASE

    def test_delta_at_absolute_threshold_stays_likely_same(self) -> None:
        # Exactly 5 minutes — not "> 5", so still likely-same.
        conflict = _detect(runtime_a=120.0, runtime_b=125.0)
        assert conflict.runtime_delta_minutes == 5.0
        assert conflict.suggested_action is SuggestedAction.LIKELY_SAME_RELEASE

    def test_delta_above_absolute_but_under_relative_stays_likely_same(self) -> None:
        # 10 min delta against a 300-min run is 3.3% — relative bound not hit.
        conflict = _detect(runtime_a=300.0, runtime_b=310.0)
        assert conflict.runtime_delta_minutes == 10.0
        assert conflict.suggested_action is SuggestedAction.LIKELY_SAME_RELEASE

    def test_delta_above_both_bounds_flags_different_edit(self) -> None:
        # 138 vs 192 — delta 54 min, > 5min AND > 10% (54/138 ≈ 39%).
        conflict = _detect(runtime_a=138.0, runtime_b=192.0)
        assert conflict.runtime_delta_minutes == 54.0
        assert conflict.suggested_action is SuggestedAction.DIFFERENT_EDIT_SUSPECTED

    def test_missing_runtime_falls_back_to_likely_same(self) -> None:
        conflict = _detect(runtime_a=None, runtime_b=120.0)
        assert conflict.runtime_delta_minutes is None
        assert conflict.suggested_action is SuggestedAction.LIKELY_SAME_RELEASE

    def test_zero_runtime_falls_back_to_likely_same(self) -> None:
        # Avoids division-by-zero when computing the relative threshold.
        conflict = _detect(runtime_a=0.0, runtime_b=10.0)
        assert conflict.suggested_action is SuggestedAction.LIKELY_SAME_RELEASE


class TestInvariants:
    """Domain invariants enforced by the aggregate."""

    def test_self_collision_is_rejected(self) -> None:
        with pytest.raises(DomainValidationException):
            MediaConflict.detect(
                candidate_a_id=_A,
                candidate_a_type="movie",
                candidate_a_runtime_minutes=120.0,
                candidate_b_id=_A,
                candidate_b_type="movie",
                candidate_b_runtime_minutes=120.0,
                match_reason=MatchReason.TMDB_ID,
            )

    def test_negative_runtime_delta_is_rejected(self) -> None:
        with pytest.raises(DomainValidationException):
            MediaConflict(
                candidate_a_id=_A,
                candidate_a_type="movie",
                candidate_b_id=_B,
                candidate_b_type="movie",
                match_reason=MatchReason.TMDB_ID,
                runtime_delta_minutes=-1.0,
                suggested_action=SuggestedAction.LIKELY_SAME_RELEASE,
            )

    def test_partial_resolution_state_is_rejected(self) -> None:
        # ``resolved_at`` without ``resolution`` is inconsistent.
        with pytest.raises(DomainValidationException):
            MediaConflict(
                candidate_a_id=_A,
                candidate_a_type="movie",
                candidate_b_id=_B,
                candidate_b_type="movie",
                match_reason=MatchReason.TMDB_ID,
                runtime_delta_minutes=0.0,
                suggested_action=SuggestedAction.LIKELY_SAME_RELEASE,
                resolved_at=datetime.now(UTC),
                resolution=None,
            )


class TestResolve:
    """``resolve()`` transitions the aggregate to its terminal state."""

    def test_resolve_stamps_timestamp_and_action(self) -> None:
        conflict = _detect()
        resolved = conflict.resolve(ResolutionAction.MERGE_KEEP_BOTH, winner_id=_A)

        assert resolved.is_resolved is True
        assert resolved.resolution is ResolutionAction.MERGE_KEEP_BOTH
        assert resolved.resolved_at is not None
        assert resolved.winner_id == _A
        assert resolved.loser_id() == _B

    def test_resolve_returns_a_new_instance(self) -> None:
        conflict = _detect()
        resolved = conflict.resolve(ResolutionAction.MARK_DISTINCT)
        assert resolved is not conflict
        assert conflict.is_resolved is False  # original untouched
        assert resolved.is_marked_distinct is True
        assert resolved.winner_id is None
        assert resolved.loser_id() is None

    def test_resolving_twice_raises(self) -> None:
        conflict = _detect()
        resolved = conflict.resolve(ResolutionAction.MERGE_REPLACE, winner_id=_B)
        with pytest.raises(BusinessRuleViolationException):
            resolved.resolve(ResolutionAction.MARK_DISTINCT)


class TestWinnerIdInvariants:
    """``winner_id`` semantics enforced by the aggregate."""

    def test_merge_requires_winner_id(self) -> None:
        conflict = _detect()
        with pytest.raises(DomainValidationException):
            conflict.resolve(ResolutionAction.MERGE_REPLACE)

    def test_mark_distinct_rejects_winner_id(self) -> None:
        conflict = _detect()
        with pytest.raises(DomainValidationException):
            conflict.resolve(ResolutionAction.MARK_DISTINCT, winner_id=_A)

    def test_winner_id_must_be_one_of_candidates(self) -> None:
        conflict = _detect()
        with pytest.raises(DomainValidationException):
            conflict.resolve(ResolutionAction.MERGE_REPLACE, winner_id="mov_cccccccccccc")


class TestResolutionSourceInvariants:
    """``resolution_source`` semantics enforced by the aggregate (ADR-015 Phase 3)."""

    def test_manual_resolution_is_default_source(self) -> None:
        conflict = _detect()
        resolved = conflict.resolve(ResolutionAction.MERGE_REPLACE, winner_id=_A)
        assert resolved.resolution_source is ResolutionSource.MANUAL
        assert resolved.is_auto_resolved is False

    def test_auto_source_explicitly_marks_aggregate(self) -> None:
        conflict = _detect()
        resolved = conflict.resolve(
            ResolutionAction.MERGE_REPLACE,
            winner_id=_A,
            source=ResolutionSource.AUTO,
        )
        assert resolved.resolution_source is ResolutionSource.AUTO
        assert resolved.is_auto_resolved is True

    def test_auto_source_rejected_for_mark_distinct(self) -> None:
        # AUTO is only for the orphan-merge path; MARK_DISTINCT is
        # always a deliberate operator decision.
        conflict = _detect()
        with pytest.raises(DomainValidationException):
            conflict.resolve(
                ResolutionAction.MARK_DISTINCT,
                source=ResolutionSource.AUTO,
            )

    def test_resolution_source_forbidden_on_pending_rows(self) -> None:
        # Directly constructing a pending row with a source set is invalid.
        with pytest.raises(DomainValidationException):
            MediaConflict(
                candidate_a_id=_A,
                candidate_a_type="movie",
                candidate_b_id=_B,
                candidate_b_type="movie",
                match_reason=MatchReason.TMDB_ID,
                runtime_delta_minutes=0.0,
                suggested_action=SuggestedAction.LIKELY_SAME_RELEASE,
                resolution_source=ResolutionSource.MANUAL,
            )
