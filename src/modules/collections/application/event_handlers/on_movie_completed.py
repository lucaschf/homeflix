"""Cross-BC handler: take a finished movie off the profile's watchlist."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWorkFactory,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.integration_events import MovieCompletedEvent

_logger = logging.getLogger(__name__)


class OnMovieCompletedHandler(EventHandler):
    """Remove a movie from a profile's watchlist once that profile finishes it.

    The watchlist is the "quero assistir" list (RF-018): watching the
    movie fulfils the entry. Only movies arrive here; a series stays on
    the list until the profile removes it, since new seasons keep coming.
    Custom lists are curated by hand and keep the movie.

    Removing a movie that is not on the watchlist is a no-op, so the
    handler is safe to run for every finished movie.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MovieCompletedEvent``."""
        if not isinstance(event, MovieCompletedEvent):
            return

        async with self._uow_factory() as uow:
            removed = await uow.watchlist.remove(
                CollectionMediaId(event.movie_id.value), event.profile_id
            )

        if removed:
            _logger.info(
                "Removed finished movie %s from profile %s's watchlist",
                event.movie_id,
                event.profile_id,
            )


__all__ = ["OnMovieCompletedHandler"]
