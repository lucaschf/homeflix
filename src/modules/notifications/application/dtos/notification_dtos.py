"""DTOs for the notification use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.modules.notifications.domain.entities import Notification
    from src.modules.notifications.domain.value_objects import NotificationKind


@dataclass(frozen=True)
class CreateNotificationInput:
    """Input for ``CreateNotificationUseCase``.

    Attributes:
        recipient_user_id: External id (``usr_xxx``) of the user
            who should see the notification.
        kind: Discriminator picked up by the frontend renderer.
        title: Short headline shown in the inbox row.
        body: Optional subtitle.
        payload: Kind-specific extras (deep-link target, etc.).
            Stored as JSON.
    """

    recipient_user_id: str
    kind: NotificationKind
    title: str
    body: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ListUserNotificationsInput:
    """Input for ``ListUserNotificationsUseCase``.

    Attributes:
        recipient_user_id: External id of the caller — the use
            case never accepts an arbitrary user id from the
            request body; the route fills this from the auth
            context so a user can't read another user's inbox.
        unread_only: When ``True``, restrict the listing to rows
            that still count toward the badge.
        limit: Page size. Defaults to 50.
    """

    recipient_user_id: str
    unread_only: bool = False
    limit: int = 50


@dataclass(frozen=True)
class MarkNotificationReadInput:
    """Input for ``MarkNotificationReadUseCase``.

    Attributes:
        notification_id: External id (``nfy_xxx``) of the row to
            mark read.
        recipient_user_id: External id of the caller — the use
            case scopes the lookup by this field so a user can't
            mark another user's notification read.
    """

    notification_id: str
    recipient_user_id: str


@dataclass(frozen=True)
class MarkAllNotificationsReadInput:
    """Input for ``MarkAllNotificationsReadUseCase``.

    Attributes:
        recipient_user_id: External id of the caller. The route
            fills this from the auth context so a user can't
            clear another user's inbox.
    """

    recipient_user_id: str


@dataclass(frozen=True)
class MarkAllNotificationsReadOutput:
    """Output for ``MarkAllNotificationsReadUseCase``.

    Attributes:
        marked_read: How many rows transitioned from unread to
            read on this call. ``0`` when the inbox was already
            clean — the route still returns 200 so the frontend
            doesn't have to branch on the empty case.
    """

    marked_read: int


@dataclass(frozen=True)
class NotificationOutput:
    """Output representation of a notification.

    Attributes:
        id: External notification id (``nfy_xxx``).
        recipient_user_id: External id of the recipient.
        kind: Notification discriminator.
        title: Short headline.
        body: Optional subtitle.
        payload: Kind-specific extras.
        is_read: ``True`` once the user has opened the notification.
        read_at: ISO-8601 read timestamp, or ``None`` if unread.
        created_at: ISO-8601 creation timestamp.
    """

    id: str
    recipient_user_id: str
    kind: str
    title: str
    body: str | None
    payload: dict[str, Any]
    is_read: bool
    read_at: str | None
    created_at: str

    @classmethod
    def from_entity(cls, entity: Notification) -> NotificationOutput:
        """Build the DTO from a domain ``Notification`` aggregate."""
        return cls(
            id=str(entity.id),
            recipient_user_id=entity.recipient_user_id,
            kind=entity.kind.value,
            title=entity.title,
            body=entity.body,
            payload=dict(entity.payload),
            is_read=entity.is_read,
            read_at=entity.read_at.isoformat() if entity.read_at else None,
            created_at=entity.created_at.isoformat(),
        )


__all__ = [
    "CreateNotificationInput",
    "ListUserNotificationsInput",
    "MarkNotificationReadInput",
    "NotificationOutput",
]
