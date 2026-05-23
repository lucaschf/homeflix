"""Post-enrich conflict detector for Movie aggregates (ADR-015 Phase 1)."""

import logging

from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.conflict_dtos import (
    DetectMovieConflictsInput,
    DetectMovieConflictsOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import MediaConflict
from src.modules.media.domain.entities.media_conflict import MatchReason
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.events import MediaConflictDetectedEvent

_logger = logging.getLogger(__name__)


class DetectMovieConflictsUseCase:
    """Materialise content-identity collisions for a freshly-enriched movie.

    Triggered by the post-enrich event handler (``MediaEnrichedEvent``).
    Looks up every other non-deleted movie sharing the same TMDB id,
    skips pairs already queued as pending, and persists a fresh
    ``MediaConflict`` for the rest. Each newly-created conflict
    publishes a ``MediaConflictDetectedEvent`` outside the UoW.

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
        input_dto: DetectMovieConflictsInput,
    ) -> DetectMovieConflictsOutput:
        """Run the detector for one enriched movie.

        Returns:
            Summary with the number and ids of conflicts persisted.
        """
        created_ids: list[str] = []
        events_to_publish: list[MediaConflictDetectedEvent] = []

        async with self._uow_factory() as uow:
            candidates = await uow.movies.find_all_by_tmdb_id(input_dto.tmdb_id)
            others = [m for m in candidates if str(m.id) != input_dto.media_id]
            if not others:
                return DetectMovieConflictsOutput(conflicts_created=0, conflict_ids=[])

            # Re-fetch self so we have its current runtime — the
            # event payload doesn't carry it.
            self_movie = next(
                (m for m in candidates if str(m.id) == input_dto.media_id),
                None,
            )
            if self_movie is None:
                # Defensive: detector fired but the enriched movie
                # vanished between commit and handler dispatch. Skip
                # rather than fabricate a pair.
                _logger.warning(
                    "Enriched movie %s not found during conflict detection",
                    input_dto.media_id,
                )
                return DetectMovieConflictsOutput(conflicts_created=0, conflict_ids=[])

            self_runtime = _runtime_minutes(self_movie)

            for other in others:
                existing = await uow.media_conflicts.find_pending_by_pair(
                    input_dto.media_id,
                    str(other.id),
                )
                if existing is not None:
                    continue

                conflict = MediaConflict.detect(
                    candidate_a_id=input_dto.media_id,
                    candidate_a_type="movie",
                    candidate_a_runtime_minutes=self_runtime,
                    candidate_b_id=str(other.id),
                    candidate_b_type="movie",
                    candidate_b_runtime_minutes=_runtime_minutes(other),
                    match_reason=MatchReason.TMDB_ID,
                )
                persisted = await uow.media_conflicts.save(conflict)
                created_ids.append(str(persisted.id))
                events_to_publish.append(
                    MediaConflictDetectedEvent(
                        conflict_id=str(persisted.id),
                        candidate_a_id=persisted.candidate_a_id,
                        candidate_b_id=persisted.candidate_b_id,
                        match_reason=persisted.match_reason.value,
                        suggested_action=persisted.suggested_action.value,
                    ),
                )

        # Publish outside the UoW so a slow subscriber doesn't hold
        # the write transaction open.
        if self._event_bus is not None:
            for event in events_to_publish:
                await self._event_bus.publish(event)

        return DetectMovieConflictsOutput(
            conflicts_created=len(created_ids),
            conflict_ids=created_ids,
        )


def _runtime_minutes(movie: Movie) -> float | None:
    """Convert ``Movie.duration`` (seconds) to minutes, or ``None`` when zero."""
    if movie.duration.value <= 0:
        return None
    return movie.duration.value / 60.0


__all__ = ["DetectMovieConflictsUseCase"]
