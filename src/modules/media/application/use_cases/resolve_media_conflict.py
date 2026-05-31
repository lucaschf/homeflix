"""Admin-driven resolution of a queued media conflict (ADR-015 Phase 2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.application.dtos.conflict_dtos import (
    ResolveMediaConflictInput,
    ResolveMediaConflictOutput,
)
from src.modules.media.domain.entities.media_conflict import (
    MediaConflict,
    ResolutionAction,
)
from src.modules.media.domain.events import MovieMergedEvent
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import MovieId
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId

if TYPE_CHECKING:
    from src.building_blocks.application.event_bus import EventBus
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory

_logger = logging.getLogger(__name__)


class ResolveMediaConflictUseCase:
    """Apply an admin's chosen disposition to a pending conflict.

    Phase 1 only writes Movie-vs-Movie conflicts, so this use case
    handles the same shape:

    - ``MARK_DISTINCT``: just stamps the row; the detector will not
      re-queue the pair (see ``find_blocking_pair``).
    - ``MERGE_REPLACE``: soft-deletes the loser movie; downstream
      ``MovieMergedEvent`` handlers repoint watch progress + list
      memberships from loser → winner.
    - ``MERGE_KEEP_BOTH``: first transfers the loser's file variants
      onto the winner, then proceeds as ``MERGE_REPLACE``.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        event_bus: Optional event bus. When ``None`` no events are
            published — handy for unit tests.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        event_bus: EventBus | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._event_bus = event_bus

    async def execute(
        self,
        input_dto: ResolveMediaConflictInput,
    ) -> ResolveMediaConflictOutput:
        """Resolve a single conflict by id.

        Returns:
            Summary of the resolution (action, winner/loser ids,
            variants transferred).
        """
        try:
            action = ResolutionAction(input_dto.action)
        except ValueError as exc:
            raise DomainValidationException(
                message=f"Unknown resolution action '{input_dto.action}'",
                message_code=MediaRuleCodes.INVALID_RESOLUTION_ACTION,
                object_type="MediaConflict",
            ) from exc

        event_to_publish: MovieMergedEvent | None = None
        variants_transferred = 0

        async with self._uow_factory() as uow:
            conflict = await uow.media_conflicts.find_by_id(
                MediaConflictId(input_dto.conflict_id),
            )
            if conflict is None:
                raise ResourceNotFoundException.for_resource(
                    "MediaConflict",
                    input_dto.conflict_id,
                )
            if conflict.is_resolved:
                raise BusinessRuleViolationException(
                    message="MediaConflict is already resolved",
                    message_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
                    rule_code=MediaRuleCodes.MEDIA_CONFLICT_ALREADY_RESOLVED,
                )

            if action is not ResolutionAction.MARK_DISTINCT:
                _ensure_movie_pair(conflict)
                _ensure_winner_in_pair(conflict, input_dto.winner_id)
            elif input_dto.winner_id is not None:
                raise DomainValidationException(
                    message="winner_id must be None for mark_distinct",
                    message_code="MEDIA_CONFLICT_WINNER_NOT_ALLOWED",
                    object_type="MediaConflict",
                )

            resolved = conflict.resolve(action, winner_id=input_dto.winner_id)
            persisted = await uow.media_conflicts.save(resolved)

            if action is ResolutionAction.MARK_DISTINCT:
                return ResolveMediaConflictOutput(
                    conflict_id=str(persisted.id),
                    action=action.value,
                    winner_id=None,
                    loser_id=None,
                    variants_transferred=0,
                )

            # MERGE branches: aggregate has validated winner_id is
            # populated and matches a candidate, so loser_id() returns
            # a non-None string. We re-fetch defensively in case the
            # invariants ever change.
            winner_id = persisted.winner_id
            loser_id = persisted.loser_id()
            if winner_id is None or loser_id is None:
                raise BusinessRuleViolationException(
                    message="MERGE resolution did not populate winner/loser",
                    message_code=MediaRuleCodes.MEDIA_CONFLICT_MERGE_INCOMPLETE,
                    rule_code=MediaRuleCodes.MEDIA_CONFLICT_MERGE_INCOMPLETE,
                )

            if action is ResolutionAction.MERGE_KEEP_BOTH:
                variants_transferred = await uow.movies.transfer_file_variants_between_movies(
                    source_movie_id=MovieId(loser_id),
                    target_movie_id=MovieId(winner_id),
                )

            deleted = await uow.movies.delete(MovieId(loser_id))
            if not deleted:
                # The loser already vanished before we got here —
                # treat the resolve as still successful (the conflict
                # row is stamped) but log so the operator notices.
                _logger.warning(
                    "Loser movie %s missing during merge resolve of %s",
                    loser_id,
                    persisted.id,
                )

            event_to_publish = MovieMergedEvent(
                conflict_id=str(persisted.id),
                winner_id=winner_id,
                loser_id=loser_id,
                keep_loser_variants=action is ResolutionAction.MERGE_KEEP_BOTH,
            )

        # Publish outside the UoW so a slow handler doesn't hold the
        # write transaction open. Cross-BC handlers (watch_progress,
        # collections) repoint FK refs from loser → winner.
        if event_to_publish is not None and self._event_bus is not None:
            await self._event_bus.publish(event_to_publish)

        return ResolveMediaConflictOutput(
            conflict_id=str(persisted.id),
            action=action.value,
            winner_id=persisted.winner_id,
            loser_id=persisted.loser_id(),
            variants_transferred=variants_transferred,
        )


def _ensure_movie_pair(conflict: MediaConflict) -> None:
    """Reject cross-type conflicts the use case is not equipped to handle."""
    if conflict.candidate_a_type != "movie" or conflict.candidate_b_type != "movie":
        raise DomainValidationException(
            message="ResolveMediaConflictUseCase only handles movie-vs-movie conflicts",
            message_code="MEDIA_CONFLICT_UNSUPPORTED_CANDIDATE_TYPE",
            object_type="MediaConflict",
        )


def _ensure_winner_in_pair(conflict: MediaConflict, winner_id: str | None) -> None:
    """Pre-validate ``winner_id`` so the aggregate's pydantic check never fires.

    Validating here keeps the resulting ``DomainValidationException`` free
    of pydantic-injected ``input`` metadata (which would carry the
    aggregate's datetime fields and trip the JSON response serializer).
    """
    if winner_id is None:
        raise DomainValidationException(
            message="winner_id is required for merge_keep_both / merge_replace",
            message_code="MEDIA_CONFLICT_WINNER_REQUIRED",
            object_type="MediaConflict",
        )
    if winner_id not in {conflict.candidate_a_id, conflict.candidate_b_id}:
        raise DomainValidationException(
            message="winner_id must be one of the conflict's candidates",
            message_code="MEDIA_CONFLICT_WINNER_NOT_IN_PAIR",
            object_type="MediaConflict",
        )


__all__ = ["ResolveMediaConflictUseCase"]
