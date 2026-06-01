"""Notification aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.notifications.domain.value_objects import (
    NotificationId,
    NotificationKind,
)
from src.shared_kernel.value_objects.media_type import MediaType

_PAYLOAD_MEDIA_TYPE_KEY = "media_type"


class Notification(AggregateRoot[NotificationId]):
    """A single in-app notification addressed to one user.

    Notifications are per-recipient (no broadcast / no fan-out
    table) so the read-side stays a straight ``WHERE
    recipient_user_id = ?`` query. The aggregate is intentionally
    small: render data lives in ``title`` / ``body`` and any extra
    deep-link state (``tmdb_id``, ``media_id``, etc.) sits in the
    free-form ``payload`` JSON so adding a new kind doesn't
    require an ALTER TABLE.

    Attributes:
        id: External ID (``nfy_xxx``).
        recipient_user_id: External id (``usr_xxx``) of the user
            who should see this notification.
        kind: Discriminator for the frontend renderer / icon.
        title: Short headline rendered in the dropdown row.
        body: Optional one-line subtitle (may be ``None`` for
            kinds whose title is self-explanatory).
        payload: Kind-specific extras consumed by the renderer
            (e.g. ``{"tmdb_id": 348, "media_type": "movie",
            "media_id": "mov_abc"}`` for a fulfilled catalog
            request). Stored as JSON so new payload shapes don't
            require a migration.
        read_at: Timestamp at which the user opened the
            notification. ``None`` while it still counts toward
            the unread badge.

    Example:
        >>> n = Notification.create(
        ...     recipient_user_id="usr_alice",
        ...     kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
        ...     title="Alien chegou ao catálogo",
        ...     body="O filme que você solicitou já está disponível.",
        ...     payload={"tmdb_id": 348, "media_id": "mov_abc",
        ...              "media_type": "movie"},
        ... )
    """

    id: NotificationId | None = Field(default=None)

    recipient_user_id: str
    kind: NotificationKind
    title: str
    body: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_payload_media_type(self) -> Notification:
        """Reject a ``media_type`` in the payload that isn't a real MediaType.

        The payload is free-form JSON, but the renderer keys deep-links
        off ``media_type``. Validating it here (ADR-016) turns a producer
        typo into an immediate error at write time instead of a silently
        broken click-through that only surfaces in the frontend.
        """
        raw = self.payload.get(_PAYLOAD_MEDIA_TYPE_KEY)
        if raw is not None:
            try:
                MediaType(raw)
            except ValueError as exc:
                raise ValueError(
                    f"payload {_PAYLOAD_MEDIA_TYPE_KEY!r} must be a valid MediaType, got {raw!r}"
                ) from exc
        return self

    @classmethod
    def create(
        cls,
        recipient_user_id: str,
        kind: NotificationKind,
        title: str,
        body: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        """Factory with automatic ID generation.

        Args:
            recipient_user_id: External id of the recipient.
            kind: Notification discriminator.
            title: Short headline shown in the inbox row.
            body: Optional one-line subtitle.
            payload: Kind-specific extras for the renderer.
                Defaults to an empty dict so the field is always
                a valid JSON object on the wire.

        Returns:
            A new ``Notification`` instance.
        """
        return cls(
            id=NotificationId.generate(),
            recipient_user_id=recipient_user_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload if payload is not None else {},
            read_at=None,
        )

    @property
    def is_read(self) -> bool:
        """``True`` once the user has opened the notification."""
        return self.read_at is not None

    def mark_read(self, read_at: datetime | None = None) -> Notification:
        """Return a copy stamped as read.

        Idempotent: re-marking an already-read row just refreshes
        the timestamp (and ``updated_at``), but the use case
        short-circuits before calling this when the row is read
        so no spurious writes happen.

        Args:
            read_at: Override timestamp (useful in tests). Defaults
                to ``datetime.now(UTC)``.

        Returns:
            A new ``Notification`` with ``read_at`` populated.
        """
        return self.with_updates(read_at=read_at or datetime.now(UTC))


__all__ = ["Notification"]
