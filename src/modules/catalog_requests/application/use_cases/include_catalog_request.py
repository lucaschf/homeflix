"""IncludeCatalogRequestUseCase — admin marks a request as available."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.catalog_requests.application.dtos import (
    CatalogRequestOutput,
    IncludeCatalogRequestInput,
)
from src.modules.catalog_requests.application.ports import CatalogArrivalNotification
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId

if TYPE_CHECKING:
    from src.modules.catalog_requests.application.ports import NotificationPublisherPort
    from src.modules.catalog_requests.application.unit_of_work import (
        CatalogRequestsUnitOfWorkFactory,
    )
    from src.modules.catalog_requests.domain.entities import CatalogRequest

_logger = logging.getLogger(__name__)


class IncludeCatalogRequestUseCase:
    """Admin "Marcar como incluído": fulfill + fan out + archive (ADR-022).

    The manual counterpart to the auto-fulfillment loop, for the
    orphan-rescue case: the title is in the catalog but the request
    never auto-matched (it landed under a different tmdb id). Marking
    it included stamps ``fulfilled_at`` — so the request leaves the
    pending queue — and pings every subscriber "já disponível".

    No local media is resolved here, so the arrival notification
    carries no ``media_id``; the renderer falls back to search instead
    of a precise deep-link (the chosen trade-off for a plain
    confirm-only admin action).

    Idempotent: an already-fulfilled request is returned unchanged
    without re-notifying.
    """

    def __init__(
        self,
        uow_factory: CatalogRequestsUnitOfWorkFactory,
        notification_publisher: NotificationPublisherPort | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory for the Catalog Requests UoW.
            notification_publisher: Optional cross-BC publisher. ``None``
                still fulfills the request (the queue closes); only the
                user-facing fanout is skipped.
        """
        self._uow_factory = uow_factory
        self._notification_publisher = notification_publisher

    async def execute(
        self,
        input_dto: IncludeCatalogRequestInput,
    ) -> CatalogRequestOutput:
        """Mark the request fulfilled and fan out the arrival ping.

        Raises:
            ResourceNotFoundException: When no active request matches.
        """
        request_id = CatalogRequestId(input_dto.request_id)
        subscriber_ids: list[str] = []
        async with self._uow_factory() as uow:
            request = await uow.catalog_requests.find_by_id(request_id)
            if request is None:
                raise ResourceNotFoundException.for_resource(
                    "CatalogRequest",
                    input_dto.request_id,
                )
            if request.is_fulfilled:
                return CatalogRequestOutput.from_entity(request)

            request = await uow.catalog_requests.update(request.mark_fulfilled())
            if self._notification_publisher is not None:
                subscriptions = await uow.catalog_subscriptions.list_for_request(
                    cast(CatalogRequestId, request.id),
                )
                subscriber_ids = [sub.user_id for sub in subscriptions]

        await self._fan_out(request, subscriber_ids)
        return CatalogRequestOutput.from_entity(request)

    async def _fan_out(
        self,
        request: CatalogRequest,
        subscriber_ids: list[str],
    ) -> None:
        """Publish "já disponível" to each subscriber, isolated per recipient."""
        if self._notification_publisher is None or not subscriber_ids:
            return

        title = request.title or f"tmdb/{request.media_type.value}/{request.tmdb_id}"
        for user_id in subscriber_ids:
            try:
                await self._notification_publisher.publish_catalog_arrival(
                    CatalogArrivalNotification(
                        recipient_user_id=user_id,
                        title=title,
                        tmdb_id=request.tmdb_id,
                        media_id=None,
                        media_type=request.media_type.value,
                    ),
                )
            except Exception:
                _logger.exception(
                    "Failed to publish manual-include notification for request %s to user %s",
                    request.id,
                    user_id,
                )


__all__ = ["IncludeCatalogRequestUseCase"]
