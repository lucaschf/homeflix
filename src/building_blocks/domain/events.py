"""Base domain event and media-specific events."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Attributes:
        occurred_at: UTC timestamp when the event occurred.
    """

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MediaCreatedEvent(DomainEvent):
    """Emitted when a new movie or series is created.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
    """

    media_id: str = ""
    media_type: str = ""


__all__ = ["DomainEvent", "MediaCreatedEvent"]
