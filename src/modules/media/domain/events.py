"""Domain events for the Media bounded context."""

from dataclasses import dataclass

from src.building_blocks.domain.events import DomainEvent


@dataclass(frozen=True)
class MediaCreatedEvent(DomainEvent):
    """Emitted when a new movie or series is created.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
    """

    media_id: str = ""
    media_type: str = ""


__all__ = ["MediaCreatedEvent"]
