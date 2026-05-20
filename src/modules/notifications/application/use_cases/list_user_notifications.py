"""List the caller's notifications, newest first."""

from dataclasses import dataclass

from src.modules.notifications.application.dtos import (
    ListUserNotificationsInput,
    NotificationOutput,
)
from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWorkFactory,
)


@dataclass(frozen=True)
class ListUserNotificationsOutput:
    """Output for ``ListUserNotificationsUseCase``.

    Bundles the list with the unread count so the header bell can
    render both off a single round-trip — otherwise a separate
    badge endpoint would double the request count for every page
    transition.

    Attributes:
        items: Notifications scoped to the caller.
        unread_count: How many of the user's notifications still
            count toward the badge — independent of ``items``
            length / ``unread_only`` filter, so the badge stays
            accurate when the dropdown only shows a page.
    """

    items: list[NotificationOutput]
    unread_count: int


class ListUserNotificationsUseCase:
    """Return the user's inbox plus the unread-badge count."""

    def __init__(self, uow_factory: NotificationsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh notifications UoW.
        """
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: ListUserNotificationsInput,
    ) -> ListUserNotificationsOutput:
        """Execute the use case."""
        async with self._uow_factory() as uow:
            rows = await uow.notifications.list_for_user(
                recipient_user_id=input_dto.recipient_user_id,
                unread_only=input_dto.unread_only,
                limit=input_dto.limit,
            )
            unread_count = await uow.notifications.count_unread_for_user(
                input_dto.recipient_user_id,
            )

        return ListUserNotificationsOutput(
            items=[NotificationOutput.from_entity(n) for n in rows],
            unread_count=unread_count,
        )


__all__ = ["ListUserNotificationsOutput", "ListUserNotificationsUseCase"]
