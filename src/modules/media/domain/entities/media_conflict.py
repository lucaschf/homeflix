"""MediaConflict aggregate — pending duplicate-detection record."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar, Self

from pydantic import Field, model_validator

from src.building_blocks.domain import AggregateRoot
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId


class MatchReason(str, Enum):
    """Which identity rule fired the collision."""

    TMDB_ID = "tmdb_id"
    TITLE_YEAR_FALLBACK = "title_year_fallback"


class SuggestedAction(str, Enum):
    """Hint shown to the admin in the conflict queue.

    Computed at detection time from the runtime delta — see
    :class:`MediaConflict` for thresholds.
    """

    LIKELY_SAME_RELEASE = "likely_same_release"
    DIFFERENT_EDIT_SUSPECTED = "different_edit_suspected"


class ResolutionAction(str, Enum):
    """How the admin closed the conflict."""

    MERGE_KEEP_BOTH = "merge_keep_both"
    MERGE_REPLACE = "merge_replace"
    MARK_DISTINCT = "mark_distinct"


class MediaConflict(AggregateRoot[MediaConflictId]):
    """A detected duplicate-identity collision awaiting resolution.

    Records that two media entities (candidates A and B) appear to
    refer to the same underlying release, based on a content-identity
    rule (TMDB id match, or title+year fallback). Lives in the
    operator-facing conflict queue until resolved.

    The aggregate is polymorphic by design — candidate ids carry an
    explicit ``_type`` discriminator (``"movie"`` today; ``"series"``
    in a later phase) so the same table accommodates future expansion
    without a schema change. Phase 1 only populates ``"movie"``.

    Attributes:
        id: External id (``cnf_xxx``).
        candidate_a_id: External id of one side (e.g. ``mov_xxx``).
        candidate_a_type: ``"movie"`` (Phase 1) or ``"series"`` (later).
        candidate_b_id: External id of the other side.
        candidate_b_type: Same contract as ``candidate_a_type``.
        match_reason: Which identity rule fired.
        runtime_delta_minutes: Absolute difference between the two
            sides' runtimes, in minutes. ``None`` when one or both
            sides lack runtime data (the suggested action degrades
            to ``LIKELY_SAME_RELEASE`` in that case).
        suggested_action: Pre-computed hint for the admin queue UI.
        resolved_at: ``None`` while pending; stamped when admin
            resolves the conflict.
        resolution: Action the admin chose. Always paired with
            ``resolved_at`` — both ``None`` or both set.
    """

    # Class-level thresholds — ADR-015: delta must exceed BOTH the
    # absolute and the relative bound to be flagged as a suspected
    # different edit. Either bound alone is satisfied by routine
    # encoding/cropping differences and would over-trigger.
    RUNTIME_DELTA_ABS_MINUTES_THRESHOLD: ClassVar[float] = 5.0
    RUNTIME_DELTA_RELATIVE_THRESHOLD: ClassVar[float] = 0.10

    id: MediaConflictId | None = Field(default=None)

    candidate_a_id: str
    candidate_a_type: str
    candidate_b_id: str
    candidate_b_type: str

    match_reason: MatchReason
    runtime_delta_minutes: float | None = None
    suggested_action: SuggestedAction

    resolved_at: datetime | None = None
    resolution: ResolutionAction | None = None

    @model_validator(mode="after")
    def _validate_candidates_distinct(self) -> Self:
        """Reject self-collisions (programmer error in the detector)."""
        if self.candidate_a_id == self.candidate_b_id:
            raise ValueError("candidate_a_id and candidate_b_id must differ")
        return self

    @model_validator(mode="after")
    def _validate_runtime_delta_non_negative(self) -> Self:
        """Runtime delta is an absolute difference, never negative."""
        if self.runtime_delta_minutes is not None and self.runtime_delta_minutes < 0:
            raise ValueError("runtime_delta_minutes must be >= 0")
        return self

    @model_validator(mode="after")
    def _validate_resolution_consistency(self) -> Self:
        """``resolved_at`` and ``resolution`` move together."""
        a_set = self.resolved_at is not None
        b_set = self.resolution is not None
        if a_set != b_set:
            raise ValueError("resolved_at and resolution must both be set or both be None")
        return self

    @classmethod
    def detect(
        cls,
        *,
        candidate_a_id: str,
        candidate_a_type: str,
        candidate_a_runtime_minutes: float | None,
        candidate_b_id: str,
        candidate_b_type: str,
        candidate_b_runtime_minutes: float | None,
        match_reason: MatchReason,
    ) -> Self:
        """Build a fresh ``MediaConflict`` from a detected pair.

        Computes ``runtime_delta_minutes`` (when both runtimes are
        available) and derives ``suggested_action`` using the
        class-level thresholds.

        Returns:
            New ``MediaConflict`` instance, pending and unsaved.
        """
        delta = _compute_runtime_delta(
            candidate_a_runtime_minutes,
            candidate_b_runtime_minutes,
        )
        action = cls._derive_suggested_action(
            delta, candidate_a_runtime_minutes, candidate_b_runtime_minutes
        )
        return cls(
            candidate_a_id=candidate_a_id,
            candidate_a_type=candidate_a_type,
            candidate_b_id=candidate_b_id,
            candidate_b_type=candidate_b_type,
            match_reason=match_reason,
            runtime_delta_minutes=delta,
            suggested_action=action,
        )

    @classmethod
    def _derive_suggested_action(
        cls,
        delta_minutes: float | None,
        runtime_a: float | None,
        runtime_b: float | None,
    ) -> SuggestedAction:
        """Apply the two-bound rule from ADR-015 to derive the hint."""
        if delta_minutes is None or runtime_a is None or runtime_b is None:
            return SuggestedAction.LIKELY_SAME_RELEASE

        smaller = min(runtime_a, runtime_b)
        if smaller <= 0:
            return SuggestedAction.LIKELY_SAME_RELEASE

        exceeds_abs = delta_minutes > cls.RUNTIME_DELTA_ABS_MINUTES_THRESHOLD
        exceeds_rel = (delta_minutes / smaller) > cls.RUNTIME_DELTA_RELATIVE_THRESHOLD
        if exceeds_abs and exceeds_rel:
            return SuggestedAction.DIFFERENT_EDIT_SUSPECTED
        return SuggestedAction.LIKELY_SAME_RELEASE

    def resolve(self, action: ResolutionAction) -> Self:
        """Stamp the conflict as resolved with the chosen action.

        Idempotency: resolving an already-resolved conflict raises —
        callers must check ``is_resolved`` first or query the
        repository for the current state.

        Args:
            action: Operator's chosen disposition.

        Returns:
            New instance with ``resolved_at`` and ``resolution`` set.

        Raises:
            BusinessRuleViolationException: When the conflict has
                already been resolved.
        """
        if self.is_resolved:
            raise BusinessRuleViolationException(
                message="MediaConflict is already resolved",
                message_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
                rule_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
            )
        return self.with_updates(
            resolved_at=datetime.now(UTC),
            resolution=action,
        )

    @property
    def is_resolved(self) -> bool:
        """``True`` once the operator has dispositioned the conflict."""
        return self.resolved_at is not None


def _compute_runtime_delta(a: float | None, b: float | None) -> float | None:
    """Absolute runtime difference in minutes, or ``None`` if missing."""
    if a is None or b is None:
        return None
    return abs(a - b)


__all__ = [
    "MatchReason",
    "MediaConflict",
    "ResolutionAction",
    "SuggestedAction",
]
