"""Cross-BC handler: migrate watchlist / custom-list refs on movie promotion."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.collections.application.unit_of_work import (
    CollectionsUnitOfWorkFactory,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.modules.media.domain.events import MoviePromotedToSeriesEvent
from src.shared_kernel.value_objects import CollectionMediaType

_logger = logging.getLogger(__name__)


class OnMoviePromotedToSeriesHandler(EventHandler):
    """Repoint watchlist + custom-list entries to the new series id.

    Unlike watch progress (which gets *deleted* on promotion because
    a half-watched position can't survive a re-cut episode boundary
    safely), collection memberships are pure "I want to watch this
    content" markers — they should survive the structural change so
    the user's lists don't quietly lose items. The same content is
    still there, just now organised as a series instead of a movie.

    Both writes run in the same Unit of Work so a partial failure
    (e.g. watchlist rewritten but DB crashes before custom-lists)
    rolls back, keeping the two tables consistent.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MoviePromotedToSeriesEvent``."""
        if not isinstance(event, MoviePromotedToSeriesEvent):
            return

        async with self._uow_factory() as uow:
            from_media_id = CollectionMediaId(event.movie_id.value)
            to_media_id = CollectionMediaId(event.series_id.value)
            watchlist_updated = await uow.watchlist.rewrite_media_id(
                from_media_id=from_media_id,
                to_media_id=to_media_id,
                to_media_type=CollectionMediaType.SERIES,
            )
            lists_updated = await uow.custom_lists.rewrite_item_media_id(
                from_media_id=from_media_id,
                to_media_id=to_media_id,
                to_media_type=CollectionMediaType.SERIES,
            )

        if watchlist_updated or lists_updated:
            _logger.info(
                "Repointed %d watchlist + %d custom-list entries " "from movie %s to series %s",
                watchlist_updated,
                lists_updated,
                event.movie_id,
                event.series_id,
            )


__all__ = ["OnMoviePromotedToSeriesHandler"]
