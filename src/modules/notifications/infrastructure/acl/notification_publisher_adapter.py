"""Adapter implementing ``NotificationPublisherPort`` for catalog_requests.

This is the only file in the Notifications BC that imports from
a port defined in another bounded context. The adapter delegates
to ``CreateNotificationUseCase`` so all the per-kind copy /
payload shaping stays on this side of the boundary — Catalog
Requests just hands over a typed DTO and never has to know
anything about ``Notification`` aggregates or their fields.
"""

from src.modules.catalog_requests.application.ports.notification_publisher_port import (
    CatalogArrivalNotification,
    NotificationPublisherPort,
)
from src.modules.notifications.application.dtos import CreateNotificationInput
from src.modules.notifications.application.use_cases import CreateNotificationUseCase
from src.modules.notifications.domain.value_objects import NotificationKind


class NotificationPublisherAdapter(NotificationPublisherPort):
    """Translate a catalog-arrival event into a notification row."""

    def __init__(self, create_notification: CreateNotificationUseCase) -> None:
        """Initialize the adapter.

        Args:
            create_notification: The notifications-side use case
                that persists the row. Injected rather than the
                UoW factory so the adapter stays free of the
                domain-layer Notification import — the use case
                already encapsulates ``Notification.create``.
        """
        self._create_notification = create_notification

    async def publish_catalog_arrival(
        self,
        notification: CatalogArrivalNotification,
    ) -> None:
        """Create the user-facing notification row.

        The body line stays untranslated for now — the frontend
        falls back to a kind-specific template keyed off the
        ``payload`` when ``body`` is ``None``, so the publisher
        doesn't have to bake the user's locale in here.
        """
        await self._create_notification.execute(
            CreateNotificationInput(
                recipient_user_id=notification.recipient_user_id,
                kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
                title=notification.title,
                body=None,
                payload={
                    "tmdb_id": notification.tmdb_id,
                    "media_id": (notification.media_id.value if notification.media_id else None),
                    "media_type": notification.media_type,
                },
            ),
        )


__all__ = ["NotificationPublisherAdapter"]
