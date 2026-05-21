"""Repository interface for ``Notification`` aggregates."""

from abc import ABC, abstractmethod

from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import NotificationId


class NotificationRepository(ABC):
    """Abstract repository for ``Notification`` persistence.

    Always scoped by ``recipient_user_id`` on reads — a notification
    addressed to one user must never leak into another's inbox,
    even by accident. Writes don't need a scope because the
    recipient is part of the aggregate itself.
    """

    @abstractmethod
    async def add(self, notification: Notification) -> Notification:
        """Persist a new notification.

        Args:
            notification: The aggregate to persist. Must have an ``id``.

        Returns:
            The persisted aggregate, refreshed from the database.
        """

    @abstractmethod
    async def update(self, notification: Notification) -> Notification:
        """Update an existing notification.

        Args:
            notification: The updated aggregate.

        Returns:
            The persisted aggregate, refreshed from the database.
        """

    @abstractmethod
    async def find_by_id_for_user(
        self,
        notification_id: NotificationId,
        recipient_user_id: str,
    ) -> Notification | None:
        """Look up a notification by id, scoped to the recipient.

        The owner check is part of the lookup so a route can't
        accidentally mutate a notification belonging to another
        user just because it has the id.

        Args:
            notification_id: External id (``nfy_xxx``).
            recipient_user_id: The user whose inbox the row must
                belong to.

        Returns:
            The matching ``Notification`` or ``None`` when no
            non-deleted row matches both fields.
        """

    @abstractmethod
    async def list_for_user(
        self,
        recipient_user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications addressed to a user, newest first.

        Args:
            recipient_user_id: External id of the recipient.
            unread_only: When ``True``, restrict to rows with
                ``read_at IS NULL``.
            limit: Cap on the number of rows returned. Defaults to
                50 — large enough that the dropdown rarely
                paginates, small enough to keep the query cheap.

        Returns:
            Notifications ordered by ``created_at`` descending.
        """

    @abstractmethod
    async def count_unread_for_user(self, recipient_user_id: str) -> int:
        """Return the unread-badge count for a user.

        Used by the header bell to render the red dot without
        downloading the full list.

        Args:
            recipient_user_id: External id of the recipient.

        Returns:
            Number of non-deleted notifications with ``read_at IS NULL``.
        """

    @abstractmethod
    async def mark_all_read_for_user(self, recipient_user_id: str) -> int:
        """Stamp every unread notification of a user as read.

        Powers the "Marcar todas como lidas" action in the header
        bell. Implemented as a single bulk ``UPDATE`` instead of an
        N+1 fetch-then-update so a long-untouched inbox flips in
        one round-trip. Already-read rows are left alone so the
        original ``read_at`` doesn't move.

        Args:
            recipient_user_id: External id of the recipient.

        Returns:
            Count of rows that were flipped from unread to read on
            this call. ``0`` when the inbox was already clean.
        """


__all__ = ["NotificationRepository"]
