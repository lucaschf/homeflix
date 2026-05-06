"""Base classes for Domain Entities and Aggregate Roots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Self, TypeVar

if TYPE_CHECKING:
    from src.building_blocks.domain.events import DomainEvent

from pydantic import ConfigDict, Field, PrivateAttr, ValidationError

from src.building_blocks.domain.models import DomainModel, _raise_domain_validation

# Type variable for entity ID
IdT = TypeVar("IdT")


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class DomainEntity(DomainModel, Generic[IdT]):
    """Base class for Domain Entities.

    Entities have identity (id) that persists over time and lifecycle timestamps.
    Provides with_updates() for creating modified copies.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
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

    def with_updates(self, **kwargs: Any) -> Self:
        """Create a new, fully validated instance by applying updates atomically.

        Automatically bumps ``updated_at`` to the current UTC time unless
        an explicit value is provided in *kwargs*.

        Args:
            **kwargs: Fields to update with their new values.

        Returns:
            A new instance with the updates applied.

        Raises:
            DomainValidationException: If the resulting state is invalid.
        """
        kwargs.setdefault("updated_at", utc_now())

        current_data = self.model_dump()
        current_data.update(kwargs)

        try:
            return self.__class__.model_validate(current_data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)


class AggregateRoot(DomainEntity[IdT]):
    """Base class for Aggregate Roots.

    Includes domain events collection.
    """

    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def add_event(self, event: DomainEvent) -> None:
        """Add a domain event."""
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
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

    def with_updates(self, **kwargs: Any) -> Self:
        """Create a new instance with updates, moving pending events.

        Overrides DomainEntity.with_updates to ensure domain events
        survive immutable model transitions. Events are moved (not copied)
        to the new instance — the old instance is cleared to prevent
        double-dispatch if it is accidentally retained.
        """
        new_instance = super().with_updates(**kwargs)
        new_instance._events = self._events[:]
        self._events.clear()
        return new_instance


__all__ = ["AggregateRoot", "DomainEntity", "utc_now"]
