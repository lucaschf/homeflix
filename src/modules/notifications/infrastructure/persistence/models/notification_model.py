"""Notification ORM model."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class NotificationModel(Base):
    """SQLAlchemy model for ``Notification``.

    Maps to the ``notifications`` table. Each row is one in-app
    notification addressed to one user; broadcast / fan-out is
    intentionally not modeled — every producer writes one row
    per recipient.

    Attributes:
        recipient_user_id: External id (``usr_xxx``) of the user
            whose inbox this row belongs to. Indexed because every
            list query filters by it.
        kind: ``NotificationKind`` discriminator string.
        title: Short headline rendered in the dropdown row.
        body: Optional one-line subtitle.
        payload: Kind-specific extras (deep-link target, etc.)
            stored as JSON so adding a new kind doesn't require
            a migration.
        read_at: Timestamp at which the user opened the
            notification. ``NULL`` while it still counts toward
            the unread badge — indexed so the badge query stays
            cheap.
    """

    recipient_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<NotificationModel(id={self.id}, "
            f"recipient_user_id={self.recipient_user_id!r}, "
            f"kind={self.kind!r}, read={self.read_at is not None})>"
        )


__all__ = ["NotificationModel"]
