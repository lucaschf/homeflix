"""MediaConflict aggregate — pending duplicate-detection record."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar, Self

from pydantic import Field, model_validator

from src.building_blocks.domain import AggregateRoot
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects.conflict_candidate import (
    ConflictCandidate,  # noqa: TCH001 — runtime for Pydantic
)
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


class ResolutionSource(str, Enum):
    """Who closed the conflict.

    - ``MANUAL`` — the admin clicked through the resolve flow.
    - ``AUTO`` — the post-enrich detector noticed one side was
      orphaned (file missing + library root healthy) and merged it
      silently. Surfaces in a separate audit view, not the operator
      queue (see ADR-015 Phase 3).
    """

    MANUAL = "manual"
    AUTO = "auto"


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
        candidate_a: One side of the pair — its external id (e.g.
            ``mov_xxx``) and media-type discriminator (``"movie"`` in
            Phase 1, ``"series"`` in a later phase).
        candidate_b: The other side, same contract as ``candidate_a``.
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
        winner_id: For ``MERGE_*`` resolutions, the external id of the
            candidate that survived. ``None`` for pending rows and
            for ``MARK_DISTINCT`` (no winner — both sides survive).
        resolution_source: ``MANUAL`` (admin via the resolve dialog)
            or ``AUTO`` (post-enrich detector silently merging an
            orphan). ``None`` while pending; always set on resolved
            rows. Auto rows are only ever produced by ADR-015 Phase 3
            and always carry a MERGE action.
    """

    # Class-level thresholds — ADR-015: delta must exceed BOTH the
    # absolute and the relative bound to be flagged as a suspected
    # different edit. Either bound alone is satisfied by routine
    # encoding/cropping differences and would over-trigger.
    RUNTIME_DELTA_ABS_MINUTES_THRESHOLD: ClassVar[float] = 5.0
    RUNTIME_DELTA_RELATIVE_THRESHOLD: ClassVar[float] = 0.10

    id: MediaConflictId | None = Field(default=None)

    candidate_a: ConflictCandidate
    candidate_b: ConflictCandidate

    match_reason: MatchReason
    runtime_delta_minutes: float | None = None
    suggested_action: SuggestedAction

    resolved_at: datetime | None = None
    resolution: ResolutionAction | None = None
    winner_id: str | None = None
    resolution_source: ResolutionSource | None = None

    @model_validator(mode="after")
    def _validate_candidates_distinct(self) -> Self:
        """Reject self-collisions (programmer error in the detector)."""
        if self.candidate_a.id == self.candidate_b.id:
            raise ValueError("candidate_a and candidate_b must have different ids")
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

    @model_validator(mode="after")
    def _validate_winner_id_paired_with_merge(self) -> Self:
        """``winner_id`` is required for MERGE resolutions and forbidden otherwise."""
        if self.resolution in {ResolutionAction.MERGE_KEEP_BOTH, ResolutionAction.MERGE_REPLACE}:
            if self.winner_id is None:
                raise ValueError(
                    "winner_id is required for MERGE_KEEP_BOTH / MERGE_REPLACE resolutions",
                )
            if self.winner_id not in {self.candidate_a.id, self.candidate_b.id}:
                raise ValueError("winner_id must be one of the conflict's candidates")
        elif self.winner_id is not None:
            raise ValueError("winner_id must be None for pending or MARK_DISTINCT rows")
        return self

    @model_validator(mode="after")
    def _validate_resolution_source(self) -> Self:
        """``resolution_source`` is required on resolved rows; AUTO only on MERGE."""
        if self.resolved_at is None:
            if self.resolution_source is not None:
                raise ValueError("resolution_source must be None for pending rows")
            return self
        if self.resolution_source is None:
            raise ValueError("resolution_source must be set on resolved rows")
        if self.resolution_source is ResolutionSource.AUTO and self.resolution not in {
            ResolutionAction.MERGE_KEEP_BOTH,
            ResolutionAction.MERGE_REPLACE,
        }:
            raise ValueError(
                "AUTO resolution_source is only valid for MERGE_KEEP_BOTH / MERGE_REPLACE",
            )
        return self

    @classmethod
    def detect(
        cls,
        *,
        candidate_a: ConflictCandidate,
        candidate_a_runtime_minutes: float | None,
        candidate_b: ConflictCandidate,
        candidate_b_runtime_minutes: float | None,
        match_reason: MatchReason,
        abs_threshold_minutes: float | None = None,
        relative_threshold: float | None = None,
    ) -> Self:
        """Build a fresh ``MediaConflict`` from a detected pair.

        Computes ``runtime_delta_minutes`` (when both runtimes are
        available) and derives ``suggested_action`` from the
        runtime-delta heuristic.

        Args:
            candidate_a: One side of the pair (external id + media type).
            candidate_a_runtime_minutes: Runtime of side A, in minutes,
                or ``None`` when unknown.
            candidate_b: The other side, same contract as ``candidate_a``.
            candidate_b_runtime_minutes: Runtime of side B, in minutes,
                or ``None`` when unknown.
            match_reason: Which identity rule fired the collision.
            abs_threshold_minutes: Absolute runtime-delta ceiling, in
                minutes. ``None`` falls back to
                :attr:`RUNTIME_DELTA_ABS_MINUTES_THRESHOLD`. Supplied by
                the detector from the ``scan_dedup`` runtime settings
                bucket (ADR-013) so operators can tune it without a
                deploy.
            relative_threshold: Relative ceiling as a fraction of the
                shorter runtime. ``None`` falls back to
                :attr:`RUNTIME_DELTA_RELATIVE_THRESHOLD`.

        Returns:
            New ``MediaConflict`` instance, pending and unsaved.
        """
        delta = _compute_runtime_delta(
            candidate_a_runtime_minutes,
            candidate_b_runtime_minutes,
        )
        action = cls._derive_suggested_action(
            delta,
            candidate_a_runtime_minutes,
            candidate_b_runtime_minutes,
            abs_threshold_minutes=abs_threshold_minutes,
            relative_threshold=relative_threshold,
        )
        return cls(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
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
        *,
        abs_threshold_minutes: float | None = None,
        relative_threshold: float | None = None,
    ) -> SuggestedAction:
        """Apply the two-bound rule from ADR-015 to derive the hint.

        ``None`` thresholds fall back to the class-level defaults, so
        callers that don't tune the bounds keep the ADR-015 behaviour.
        """
        if delta_minutes is None or runtime_a is None or runtime_b is None:
            return SuggestedAction.LIKELY_SAME_RELEASE

        smaller = min(runtime_a, runtime_b)
        if smaller <= 0:
            return SuggestedAction.LIKELY_SAME_RELEASE

        abs_bound = (
            cls.RUNTIME_DELTA_ABS_MINUTES_THRESHOLD
            if abs_threshold_minutes is None
            else abs_threshold_minutes
        )
        rel_bound = (
            cls.RUNTIME_DELTA_RELATIVE_THRESHOLD
            if relative_threshold is None
            else relative_threshold
        )

        exceeds_abs = delta_minutes > abs_bound
        exceeds_rel = (delta_minutes / smaller) > rel_bound
        if exceeds_abs and exceeds_rel:
            return SuggestedAction.DIFFERENT_EDIT_SUSPECTED
        return SuggestedAction.LIKELY_SAME_RELEASE

    def resolve(
        self,
        action: ResolutionAction,
        *,
        winner_id: str | None = None,
        source: ResolutionSource = ResolutionSource.MANUAL,
    ) -> Self:
        """Stamp the conflict as resolved with the chosen action.

        Idempotency: resolving an already-resolved conflict raises —
        callers must check ``is_resolved`` first or query the
        repository for the current state.

        Args:
            action: Operator's chosen disposition.
            winner_id: External id of the surviving candidate. Required
                when ``action`` is ``MERGE_KEEP_BOTH`` or
                ``MERGE_REPLACE``; must be ``None`` for
                ``MARK_DISTINCT``. Validated against the candidate pair
                so a stray id cannot land in the row.
            source: Where the resolution came from — ``MANUAL`` (admin)
                or ``AUTO`` (Phase 3 silent merge of an orphan).
                ``AUTO`` is only valid with a MERGE action.

        Returns:
            New instance with ``resolved_at``, ``resolution`` and (for
            MERGE actions) ``winner_id`` set.

        Raises:
            BusinessRuleViolationException: When the conflict has
                already been resolved.
            DomainValidationException: When ``winner_id`` is missing
                for a MERGE action, provided for ``MARK_DISTINCT``, or
                not one of the candidate ids.
        """
        if self.is_resolved:
            raise BusinessRuleViolationException(
                message="MediaConflict is already resolved",
                message_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
                rule_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
            )
        self._validate_winner(action, winner_id)
        return self.with_updates(
            resolved_at=datetime.now(UTC),
            resolution=action,
            winner_id=winner_id,
            resolution_source=source,
        )

    def _validate_winner(self, action: ResolutionAction, winner_id: str | None) -> None:
        """Validate ``winner_id`` against ``action``, raising clean domain errors.

        This is the authoritative, user-facing check for the winner rule.
        The ``_validate_winner_id_paired_with_merge`` model validator stays
        as a structural invariant guarding direct construction; routing the
        resolve flow through here keeps the raised error free of the
        pydantic-injected ``input`` metadata (which would carry the
        aggregate's datetime fields and trip the JSON response serializer).

        Raises:
            DomainValidationException: When ``winner_id`` is missing for a
                MERGE action, not one of the candidates, or supplied for
                ``MARK_DISTINCT``.
        """
        is_merge = action in {ResolutionAction.MERGE_KEEP_BOTH, ResolutionAction.MERGE_REPLACE}
        if is_merge:
            if winner_id is None:
                raise DomainValidationException(
                    message="winner_id is required for merge_keep_both / merge_replace",
                    message_code=MediaRuleCodes.MEDIA_CONFLICT_WINNER_REQUIRED,
                    object_type="MediaConflict",
                )
            if winner_id not in {self.candidate_a.id, self.candidate_b.id}:
                raise DomainValidationException(
                    message="winner_id must be one of the conflict's candidates",
                    message_code=MediaRuleCodes.MEDIA_CONFLICT_WINNER_NOT_IN_PAIR,
                    object_type="MediaConflict",
                )
        elif winner_id is not None:
            raise DomainValidationException(
                message="winner_id must be None for mark_distinct",
                message_code=MediaRuleCodes.MEDIA_CONFLICT_WINNER_NOT_ALLOWED,
                object_type="MediaConflict",
            )

    @property
    def is_resolved(self) -> bool:
        """``True`` once the operator has dispositioned the conflict."""
        return self.resolved_at is not None

    @property
    def is_marked_distinct(self) -> bool:
        """``True`` when the operator declared the pair to be distinct."""
        return self.resolution is ResolutionAction.MARK_DISTINCT

    @property
    def is_auto_resolved(self) -> bool:
        """``True`` when the post-enrich detector silently merged this row."""
        return self.resolution_source is ResolutionSource.AUTO

    def loser_id(self) -> str | None:
        """For MERGE resolutions, the id of the soft-deleted side."""
        if self.winner_id is None:
            return None
        return self.candidate_b.id if self.winner_id == self.candidate_a.id else self.candidate_a.id


def _compute_runtime_delta(a: float | None, b: float | None) -> float | None:
    """Absolute runtime difference in minutes, or ``None`` if missing."""
    if a is None or b is None:
        return None
    return abs(a - b)


__all__ = [
    "MatchReason",
    "MediaConflict",
    "ResolutionAction",
    "ResolutionSource",
    "SuggestedAction",
]
