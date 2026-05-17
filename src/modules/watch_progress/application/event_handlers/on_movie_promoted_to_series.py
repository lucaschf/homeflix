"""Cross-BC handler: clear movie progress when a movie is promoted to a series."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.media.domain.events import MoviePromotedToSeriesEvent
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)

_logger = logging.getLogger(__name__)


class OnMoviePromotedToSeriesHandler(EventHandler):
    """Wipe every ``watch_progresses`` row pointing at the source movie.

    Why delete (vs. migrate the position to the new first episode):
    the agreed UX choice during PR-C design — a half-watched 3 h
    miniseries cut into two 90 min parts will almost always have the
    user's cursor in the wrong half-second after a naive remap, and
    forcing the operator to scrub manually next time is far less
    surprising than silently jumping to the middle of part 2. The
    promote dialog warns admins about this up front.

    Runs out of the event bus, which is fire-and-forget — failures
    are logged but the promote use case still reports success. A
    later retry through the regular session keeps watch_progresses
    consistent if needed.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MoviePromotedToSeriesEvent``."""
        if not isinstance(event, MoviePromotedToSeriesEvent):
            return

        async with self._uow_factory() as uow:
            deleted = await uow.progress.delete_all_for_movie(event.movie_id)

        if deleted:
            _logger.info(
                "Cleared %d watch_progress row(s) for promoted movie %s " "(now series %s)",
                deleted,
                event.movie_id,
                event.series_id,
            )


__all__ = ["OnMoviePromotedToSeriesHandler"]
