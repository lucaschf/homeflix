"""Base classes for Domain Entities and Aggregate Roots."""

from datetime import UTC, datetime
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import ConfigDict, Field, PrivateAttr

from src.domain.shared.models.domain_model import DomainModel

# Type variable for entity ID
IdT = TypeVar("IdT")


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class DomainEntity(DomainModel, Generic[IdT]):
    """Base class for Domain Entities.

    Entities have identity (id) that persists over time and lifecycle timestamps.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    id: IdT | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return False if self.id is None or other.id is None else self.id == other.id

    def __hash__(self) -> int:
        if self.id is None:
            return hash(id(self))
        return hash((self.__class__.__name__, self.id))

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utc_now()


class AggregateRoot(DomainEntity[IdT]):
    """Base class for Aggregate Roots.

    Includes domain events collection.
    """

    _events: list[Any] = PrivateAttr(default_factory=list)

    def add_event(self, event: Any) -> None:
        """Add a domain event."""
        self._events.append(event)

    def pull_events(self) -> list[Any]:
        """Retrieve and clear all pending domain events."""
        events = self._events[:]
        self._events.clear()
        return events

    def clear_events(self) -> None:
        """Clear all pending domain events."""
        self._events.clear()

    @property
    def has_pending_events(self) -> bool:
        """Return True if there are pending domain events."""
        return len(self._events) > 0


__all__ = ["AggregateRoot", "DomainEntity", "utc_now"]
