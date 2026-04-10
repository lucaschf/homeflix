"""Base domain event."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Attributes:
        occurred_at: UTC timestamp when the event occurred.
    """

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


__all__ = ["DomainEvent"]
