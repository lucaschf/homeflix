"""Mark a single notification as read."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.notifications.application.dtos import (
    MarkNotificationReadInput,
    NotificationOutput,
)
from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWorkFactory,
)
from src.modules.notifications.domain.value_objects import NotificationId


class MarkNotificationReadUseCase:
    """Flip a notification's ``read_at`` to "now" for its owner.

    Scoped on the recipient: a notification id alone is never
    enough — the use case loads the row constrained by both
    ``notification_id`` and ``recipient_user_id`` so a malicious
    or buggy caller can't mark another user's row read just by
    guessing the id. A miss raises ``ResourceNotFoundException``
    instead of leaking a permission error (no oracle on which
    ids belong to which users).

    Already-read rows short-circuit with no DB write so click
    spamming the bell doesn't generate noisy churn on
    ``updated_at``.
    """

    def __init__(self, uow_factory: NotificationsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh notifications UoW.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: MarkNotificationReadInput) -> NotificationOutput:
        """Execute the use case."""
        notification_id = NotificationId(input_dto.notification_id)
        async with self._uow_factory() as uow:
            existing = await uow.notifications.find_by_id_for_user(
                notification_id,
                input_dto.recipient_user_id,
            )
            if existing is None:
                raise ResourceNotFoundException.for_resource(
                    "Notification",
                    input_dto.notification_id,
                )
            if existing.is_read:
                return NotificationOutput.from_entity(existing)
            updated = existing.mark_read()
            persisted = await uow.notifications.update(updated)
        return NotificationOutput.from_entity(persisted)


__all__ = ["MarkNotificationReadUseCase"]
