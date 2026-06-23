"""Cross-BC handler: fulfill a pending catalog request when a title arrives."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.building_blocks.application.event_bus import EventHandler
from src.modules.catalog_requests.application.ports import (
    CatalogArrivalNotification,
    NotificationPublisherPort,
)
from src.modules.media.domain.events import MediaEnrichedEvent
from src.shared_kernel.value_objects.media_type import MediaType

if TYPE_CHECKING:
    from src.building_blocks.domain.events import DomainEvent
    from src.modules.catalog_requests.application.unit_of_work import (
        CatalogRequestsUnitOfWorkFactory,
    )
    from src.modules.catalog_requests.domain.entities import CatalogRequest

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

    When fulfillment succeeds, the handler fans a "title now
    available" ping out to every active ``CatalogSubscription`` on
    the request (ADR-022) through the optional
    ``NotificationPublisherPort`` — one notification per subscriber,
    not just the original requester. The publisher is optional so
    tests / earlier slices of the rollout can run without the
    Notifications BC wired in — fulfillment still closes the loop on
    the admin queue either way.

    Runs out of the event bus, which is fire-and-forget — failures
    here don't roll back the enrichment that just succeeded. A
    follow-up enrichment will re-emit and the loop closes on the
    next pass.
    """

    def __init__(
        self,
        uow_factory: CatalogRequestsUnitOfWorkFactory,
        notification_publisher: NotificationPublisherPort | None = None,
    ) -> None:
        """Initialize the handler.

        Args:
            uow_factory: Factory for the Catalog Requests UoW.
            notification_publisher: Optional cross-BC publisher.
                ``None`` skips the user-facing ping (the catalog
                request is still marked fulfilled) — useful for
                tests and the case where the Notifications BC
                isn't wired yet.
        """
        self._uow_factory = uow_factory
        self._notification_publisher = notification_publisher

    async def handle(self, event: DomainEvent) -> None:
        """Handle ``MediaEnrichedEvent`` by marking matching request fulfilled."""
        if not isinstance(event, MediaEnrichedEvent):
            return

        media_type = self._normalize_media_type(event.media_type)
        if media_type is None:
            return

        subscriber_ids: list[str] = []
        async with self._uow_factory() as uow:
            existing = await uow.catalog_requests.find_by_tmdb_id(
                event.tmdb_id,
                media_type,
            )
            if existing is None or existing.is_fulfilled:
                return
            fulfilled = existing.mark_fulfilled()
            await uow.catalog_requests.update(fulfilled)
            # Collect subscribers inside the UoW so the fanout has the
            # list once the session closes. Skip the query entirely when
            # there's no publisher wired (earlier rollout slices / tests).
            if self._notification_publisher is not None:
                subscriptions = await uow.catalog_subscriptions.list_for_request(
                    existing.id,
                )
                subscriber_ids = [sub.user_id for sub in subscriptions]

        _logger.info(
            "Fulfilled catalog request %s (tmdb/%s/%s → media %s); %d subscriber(s)",
            existing.id,
            event.media_type,
            event.tmdb_id,
            event.media_id,
            len(subscriber_ids),
        )

        await self._publish_arrivals(existing, event, subscriber_ids)

    @staticmethod
    def _normalize_media_type(raw: str) -> MediaType | None:
        """Coerce the event's ``media_type`` to a canonical :class:`MediaType`.

        ``MediaEnrichedEvent.media_type`` is already typed ``MediaType``,
        but the event is a plain dataclass with no runtime validation, so
        a stray vocabulary (e.g. a TMDB ``"tv"`` that should have been
        mapped upstream, or an ``"episode"``) could still be smuggled in.
        Such a value can't match any catalog request; returning ``None``
        and logging at ERROR makes the contract bug loud instead of
        letting the request linger unfulfilled in the admin queue.
        """
        try:
            return MediaType(raw)
        except ValueError:
            _logger.error(
                "MediaEnrichedEvent carried unrecognized media_type=%r; "
                "cannot fulfill the matching catalog request",
                raw,
            )
            return None

    async def _publish_arrivals(
        self,
        request: CatalogRequest,
        event: MediaEnrichedEvent,
        subscriber_ids: list[str],
    ) -> None:
        """Fan the "title now available" notification out to every subscriber.

        One ping per ``CatalogSubscription`` on the request (ADR-022),
        replacing the old single-requester path. The title falls back
        to the bare TMDB id when no snapshot exists on the request, so
        legacy rows still produce a readable row instead of a blank.
        Each publish is isolated: a failure for one subscriber is
        logged and swallowed so it can't block the others or roll back
        the fulfillment already committed.
        """
        if self._notification_publisher is None or not subscriber_ids:
            return

        title = request.title or f"tmdb/{event.media_type}/{event.tmdb_id}"
        for user_id in subscriber_ids:
            try:
                await self._notification_publisher.publish_catalog_arrival(
                    CatalogArrivalNotification(
                        recipient_user_id=user_id,
                        title=title,
                        tmdb_id=event.tmdb_id,
                        media_id=event.media_id,
                        media_type=event.media_type,
                    ),
                )
            except Exception:
                _logger.exception(
                    "Failed to publish catalog-arrival notification for request %s to user %s",
                    request.id,
                    user_id,
                )


__all__ = ["OnMediaEnrichedHandler"]
