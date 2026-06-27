"""Handler that runs the conflict detector after enrichment (ADR-015 Phase 1)."""

import logging
from collections.abc import Awaitable, Callable

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.media.application.dtos.conflict_dtos import DetectMovieConflictsInput
from src.modules.media.application.use_cases.detect_movie_conflicts import (
    DetectMovieConflictsUseCase,
)
from src.shared_kernel.integration_events import MediaEnrichedEvent
from src.shared_kernel.value_objects.media_type import MediaType

_logger = logging.getLogger(__name__)


class OnMediaEnrichedHandler(EventHandler):
    """Run the conflict detector when an enrichment locks onto a TMDB id.

    Phase 1 only handles ``media_type == "movie"``; series and episode
    enrichment events are observed but ignored until a later phase
    extends the detector. The detector is dispatched as a fresh use
    case per event so each invocation gets its own DB session.

    Args:
        detect_movie_conflicts_factory: Factory that yields a fresh
            ``DetectMovieConflictsUseCase`` per call. Async because the
            container provider builds it via async resources (session
            factory, event bus).
    """

    def __init__(
        self,
        detect_movie_conflicts_factory: Callable[[], Awaitable[DetectMovieConflictsUseCase]],
    ) -> None:
        self._detect_movie_conflicts_factory = detect_movie_conflicts_factory

    async def handle(self, event: DomainEvent) -> None:
        """Dispatch the detector for movie enrichments; ignore other media."""
        if not isinstance(event, MediaEnrichedEvent):
            return
        if event.media_type is not MediaType.MOVIE:
            # Series/episode detection is out of Phase 1 scope.
            return
        if event.tmdb_id <= 0:
            # Defensive — enrichment only publishes when tmdb_id is
            # populated, but a bad payload shouldn't crash the bus.
            _logger.warning(
                "Skipping conflict detection — missing tmdb_id for %s",
                event.media_id,
            )
            return

        use_case = await self._detect_movie_conflicts_factory()
        result = await use_case.execute(
            DetectMovieConflictsInput(
                media_id=event.media_id.value,
                tmdb_id=event.tmdb_id,
            ),
        )
        if result.conflicts_created > 0:
            _logger.info(
                "Queued %d conflict(s) for movie %s: %s",
                result.conflicts_created,
                event.media_id,
                ", ".join(result.conflict_ids),
            )


__all__ = ["OnMediaEnrichedHandler"]
