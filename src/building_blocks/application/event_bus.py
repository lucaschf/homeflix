"""Event bus and handler abstractions for the application layer."""

from abc import ABC, abstractmethod

from src.building_blocks.domain.events import DomainEvent


class EventHandler(ABC):
    """Abstract handler for a specific domain event type."""

    @abstractmethod
    async def handle(self, event: DomainEvent) -> None:
        """Handle a domain event.

        Args:
            event: The domain event to handle.
        """


class EventBus(ABC):
    """Abstract event bus for publishing and subscribing to domain events."""

    @abstractmethod
    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Register a handler for a specific event type.

        Args:
            event_type: The class of the event to listen for.
            handler: The handler to invoke when the event is published.
        """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all registered handlers.

        Args:
            event: The domain event to publish.
        """


__all__ = ["EventBus", "EventHandler"]
