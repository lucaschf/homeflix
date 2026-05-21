"""Mark every unread notification of one user as read."""

from src.modules.notifications.application.dtos import (
    MarkAllNotificationsReadInput,
    MarkAllNotificationsReadOutput,
)
from src.modules.notifications.application.unit_of_work import (
    NotificationsUnitOfWorkFactory,
)


class MarkAllNotificationsReadUseCase:
    """Bulk-clear the caller's unread inbox.

    Backs the "Marcar todas como lidas" affordance in the header
    bell. Implemented as a single bulk ``UPDATE`` at the repo
    layer — no per-row read of aggregates — so a long-untouched
    inbox flips in one round-trip. Already-read rows are left
    alone so their original ``read_at`` doesn't get rewritten.
    Idempotent: a second call returns ``marked_read=0`` without
    a DB write.
    """

    def __init__(self, uow_factory: NotificationsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh notifications UoW.
        """
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: MarkAllNotificationsReadInput,
    ) -> MarkAllNotificationsReadOutput:
        """Execute the use case."""
        async with self._uow_factory() as uow:
            marked = await uow.notifications.mark_all_read_for_user(
                input_dto.recipient_user_id,
            )
        return MarkAllNotificationsReadOutput(marked_read=marked)


__all__ = ["MarkAllNotificationsReadUseCase"]
