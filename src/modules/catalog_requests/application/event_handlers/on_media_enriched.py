"""Cross-BC handler: fulfill a pending catalog request when a title arrives."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.catalog_requests.application.unit_of_work import (
    CatalogRequestsUnitOfWorkFactory,
)
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from src.modules.media.domain.events import MediaEnrichedEvent

_logger = logging.getLogger(__name__)


class OnMediaEnrichedHandler(EventHandler):
    """Close the loop on a pending ``catalog_request`` once the title lands.

    The Media BC publishes ``MediaEnrichedEvent`` after an
    enrichment pass finishes with a populated ``tmdb_id``. This
    handler looks up the matching catalog request (if any) and
    marks it fulfilled so the admin queue stops surfacing the
    row. No request → no-op (the household never asked for this
    title). Already-fulfilled request → no-op (the event fired
    again after a force-refresh).

    Runs out of the event bus, which is fire-and-forget — failures
    here don't roll back the enrichment that just succeeded. A
    follow-up enrichment will re-emit and the loop closes on the
    next pass.
    """

    def __init__(self, uow_factory: CatalogRequestsUnitOfWorkFactory) -> None:
        """Initialize the handler.

        Args:
            uow_factory: Factory for the Catalog Requests UoW.
        """
        self._uow_factory = uow_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MediaEnrichedEvent`` by marking matching request fulfilled."""
        if not isinstance(event, MediaEnrichedEvent):
            return
        try:
            media_type = RequestedMediaType(event.media_type)
        except ValueError:
            _logger.warning(
                "MediaEnrichedEvent carried unknown media_type=%r — skipping",
                event.media_type,
            )
            return

        async with self._uow_factory() as uow:
            existing = await uow.catalog_requests.find_by_tmdb_id(
                event.tmdb_id,
                media_type,
            )
            if existing is None or existing.is_fulfilled:
                return
            fulfilled = existing.mark_fulfilled()
            await uow.catalog_requests.update(fulfilled)

        _logger.info(
            "Fulfilled catalog request %s (tmdb/%s/%s → media %s)",
            existing.id,
            event.media_type,
            event.tmdb_id,
            event.media_id,
        )


__all__ = ["OnMediaEnrichedHandler"]
