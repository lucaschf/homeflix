"""Cross-BC handler: repoint watchlist / custom-list refs on a movie merge."""

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.config.logging import get_logger
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWorkFactory,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.integration_events import MovieMergedEvent
from src.shared_kernel.value_objects import MediaType


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
        self._logger = get_logger(handler="OnMovieMergedHandler")

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MovieMergedEvent``."""
        if not isinstance(event, MovieMergedEvent):
            return

        async with self._uow_factory() as uow:
            from_media_id = CollectionMediaId(event.loser_id.value)
            to_media_id = CollectionMediaId(event.winner_id.value)
            watchlist_updated = await uow.watchlist.rewrite_media_id(
                from_media_id=from_media_id,
                to_media_id=to_media_id,
                to_media_type=MediaType.MOVIE,
            )
            lists_updated = await uow.custom_lists.rewrite_item_media_id(
                from_media_id=from_media_id,
                to_media_id=to_media_id,
                to_media_type=MediaType.MOVIE,
            )

        if watchlist_updated or lists_updated:
            self._logger.info(
                "Collection entries repointed to merged movie",
                watchlist_updated=watchlist_updated,
                lists_updated=lists_updated,
                loser_id=str(event.loser_id),
                winner_id=str(event.winner_id),
                conflict_id=event.conflict_id,
            )


__all__ = ["OnMovieMergedHandler"]
