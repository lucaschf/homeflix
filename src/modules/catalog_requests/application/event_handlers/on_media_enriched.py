"""Cross-BC handler: fulfill a pending catalog request when a title arrives."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.building_blocks.application.event_bus import EventHandler
from src.modules.catalog_requests.application.ports import (
    CatalogArrivalNotification,
    NotificationPublisherPort,
)
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from src.modules.media.domain.events import MediaEnrichedEvent
from src.shared_kernel.value_objects.media_type import MediaType

if TYPE_CHECKING:
    from src.building_blocks.domain.events import DomainEvent
    from src.modules.catalog_requests.application.unit_of_work import (
        CatalogRequestsUnitOfWorkFactory,
    )
    from src.modules.catalog_requests.domain.entities import CatalogRequest

_logger = logging.getLogger(__name__)

# Explicit ACL mapping from the Media BC's canonical MediaType to this
# BC's RequestedMediaType. Kept total over MediaType by a contract test
# so adding a MediaType member without a mapping fails CI rather than
# silently dropping arrival events in production (ADR-016).
_MEDIA_TYPE_TO_REQUESTED: dict[MediaType, RequestedMediaType] = {
    MediaType.MOVIE: RequestedMediaType.MOVIE,
    MediaType.SERIES: RequestedMediaType.SERIES,
}


class OnMediaEnrichedHandler(EventHandler):
    """Close the loop on a pending ``catalog_request`` once the title lands.

    The Media BC publishes ``MediaEnrichedEvent`` after an
    enrichment pass finishes with a populated ``tmdb_id``. This
    handler looks up the matching catalog request (if any) and
    marks it fulfilled so the admin queue stops surfacing the
    row. No request → no-op (the household never asked for this
    title). Already-fulfilled request → no-op (the event fired
    again after a force-refresh).

    When fulfillment succeeds AND the requester opted in to
    arrival notifications AND we know who they are, the handler
    pings them through the optional ``NotificationPublisherPort``.
    The publisher is optional so tests / earlier slices of the
    rollout can run without the Notifications BC wired in —
    fulfillment still closes the loop on the admin queue either
    way.

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

        media_type = self._to_requested_media_type(event.media_type)
        if media_type is None:
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

        await self._maybe_publish_arrival(existing, event)

    @staticmethod
    def _to_requested_media_type(raw: str) -> RequestedMediaType | None:
        """Translate the event's media_type to this BC's enum via the ACL map.

        Returns ``None`` (and logs at ERROR) when the value can't be
        mapped — either an unrecognized vocabulary (e.g. a stray TMDB
        ``"tv"`` that should have been mapped upstream) or a known
        :class:`MediaType` member missing from the cross-BC map. Both
        are contract bugs that must be loud, not silently dropped:
        otherwise the matching catalog request would never be marked
        fulfilled and would linger in the admin queue forever.
        """
        try:
            canonical = MediaType(raw)
        except ValueError:
            _logger.error(
                "MediaEnrichedEvent carried unrecognized media_type=%r; "
                "cannot fulfill the matching catalog request",
                raw,
            )
            return None

        mapped = _MEDIA_TYPE_TO_REQUESTED.get(canonical)
        if mapped is None:
            _logger.error(
                "No RequestedMediaType mapping for MediaType.%s; cross-BC "
                "ACL is incomplete (see _MEDIA_TYPE_TO_REQUESTED)",
                canonical.name,
            )
        return mapped

    async def _maybe_publish_arrival(
        self,
        request: CatalogRequest,
        event: MediaEnrichedEvent,
    ) -> None:
        """Dispatch the user-facing notification when conditions allow.

        Conditions: publisher wired, the requester opted in, the
        requester is known, and we have a title to show. The
        title falls back to the bare TMDB id when no snapshot
        exists on the request, so legacy rows still produce a
        readable row instead of a blank.
        """
        if self._notification_publisher is None:
            return
        if not request.notify_on_arrival:
            return
        if request.requester_user_id is None:
            return

        try:
            await self._notification_publisher.publish_catalog_arrival(
                CatalogArrivalNotification(
                    recipient_user_id=request.requester_user_id,
                    title=request.title or f"tmdb/{event.media_type}/{event.tmdb_id}",
                    tmdb_id=event.tmdb_id,
                    media_id=event.media_id.value,
                    media_type=event.media_type,
                ),
            )
        except Exception:
            # Fire-and-forget: a publisher failure can't roll back
            # the catalog-request update we already committed. Log
            # and move on — the worst case is the user doesn't see
            # the badge for this title.
            _logger.exception(
                "Failed to publish catalog-arrival notification for request %s",
                request.id,
            )


__all__ = ["OnMediaEnrichedHandler"]
