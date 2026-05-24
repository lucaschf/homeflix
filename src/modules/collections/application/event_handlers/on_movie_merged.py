"""Cross-BC handler: repoint watchlist / custom-list refs on a movie merge."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWorkFactory,
)
from src.modules.media.domain.events import MovieMergedEvent

_logger = logging.getLogger(__name__)


class OnMovieMergedHandler(EventHandler):
    """Rewrite watchlist + custom-list entries from loser → winner movie.

    Counterpart to ``OnMoviePromotedToSeriesHandler``: when two Movie
    entities are merged via the conflict queue (ADR-015 Phase 2), the
    loser's external id becomes invalid (soft-deleted) but the
    user-facing intent ("I want to watch this content") is unchanged.
    Rewriting both tables in a single Unit of Work keeps watchlist
    and custom-lists consistent.

    The underlying repository methods are idempotent and unique-aware
    — if a user already has the winner movie on their list, the loser
    entry is removed rather than producing a duplicate row.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MovieMergedEvent``."""
        if not isinstance(event, MovieMergedEvent):
            return

        async with self._uow_factory() as uow:
            watchlist_updated = await uow.watchlist.rewrite_media_id(
                from_media_id=event.loser_id,
                to_media_id=event.winner_id,
                to_media_type="movie",
            )
            lists_updated = await uow.custom_lists.rewrite_item_media_id(
                from_media_id=event.loser_id,
                to_media_id=event.winner_id,
                to_media_type="movie",
            )

        if watchlist_updated or lists_updated:
            _logger.info(
                "Repointed %d watchlist + %d custom-list entries from "
                "loser %s to winner %s (conflict %s)",
                watchlist_updated,
                lists_updated,
                event.loser_id,
                event.winner_id,
                event.conflict_id,
            )


__all__ = ["OnMovieMergedHandler"]
