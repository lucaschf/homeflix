"""Persist a new in-app notification for a specific user."""

from src.modules.notifications.application.dtos import (
    CreateNotificationInput,
    NotificationOutput,
)
from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWorkFactory,
)
from src.modules.notifications.domain.entities import Notification


class CreateNotificationUseCase:
    """Create one notification row addressed to a single user.

    Called by cross-BC adapters that need to ping a user — today
    the only producer is the catalog-request fulfillment flow, but
    the use case is intentionally generic so future kinds land
    without touching anything else.

    Example:
        >>> uc = CreateNotificationUseCase(uow_factory)
        >>> out = await uc.execute(CreateNotificationInput(
        ...     recipient_user_id="usr_alice0000000",
        ...     kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
        ...     title="Alien chegou ao catálogo",
        ...     payload={"tmdb_id": 348, "media_type": "movie",
        ...              "media_id": "mov_abc"},
        ... ))
        >>> out.is_read
        False
    """

    def __init__(self, uow_factory: NotificationsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh notifications UoW.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CreateNotificationInput) -> NotificationOutput:
        """Execute the use case."""
        notification = Notification.create(
            recipient_user_id=input_dto.recipient_user_id,
            kind=input_dto.kind,
            title=input_dto.title,
            body=input_dto.body,
            payload=dict(input_dto.payload),
        )
        async with self._uow_factory() as uow:
            persisted = await uow.notifications.add(notification)
        return NotificationOutput.from_entity(persisted)


__all__ = ["CreateNotificationUseCase"]
