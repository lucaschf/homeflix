"""Cross-BC handler: clear loser-side progress on a movie merge."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.media.domain.events import MovieMergedEvent
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)

_logger = logging.getLogger(__name__)


class OnMovieMergedHandler(EventHandler):
    """Wipe every ``watch_progresses`` row pointing at the loser movie.

    Mirrors the ``OnMoviePromotedToSeriesHandler`` reasoning: when two
    Movie entities are merged via the conflict queue (ADR-015 Phase 2),
    the loser is soft-deleted. The losing side's progress rows would
    otherwise reference a soft-deleted media id — stale data the
    catalog reads can't render. Dropping them is safer than mapping
    positions across what may be two different cuts of the same
    title (Director's Cut vs Theatrical, 720p vs 1080p remaster).

    Runs out of the event bus, which is fire-and-forget — failures
    are logged but the resolve use case still reports success.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MovieMergedEvent``."""
        if not isinstance(event, MovieMergedEvent):
            return

        async with self._uow_factory() as uow:
            deleted = await uow.progress.delete_all_for_movie(event.loser_id)

        if deleted:
            _logger.info(
                "Cleared %d watch_progress row(s) for merged loser movie %s "
                "(winner %s, conflict %s)",
                deleted,
                event.loser_id,
                event.winner_id,
                event.conflict_id,
            )


__all__ = ["OnMovieMergedHandler"]
