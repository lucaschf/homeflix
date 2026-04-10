"""In-process event bus implementation."""

import logging
from collections import defaultdict

from src.building_blocks.application.event_bus import EventBus, EventHandler
from src.building_blocks.domain.events import DomainEvent

_logger = logging.getLogger(__name__)


class InProcessEventBus(EventBus):
    """Simple in-process event bus using a dict of handlers.

    Handlers are invoked sequentially. Exceptions are logged
    but do not propagate, so a failing handler never breaks
    the publisher.

    Example:
        >>> bus = InProcessEventBus()
        >>> bus.subscribe(MyEvent, my_handler)
        >>> await bus.publish(MyEvent())
    """

    def __init__(self) -> None:
        """Initialize with empty handler registry."""
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)
        _logger.info(
            "Subscribed %s to %s",
            handler.__class__.__name__,
            event_type.__name__,
        )

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all registered handlers.

        Dispatch is by exact concrete type — handlers registered for a
        base class will not receive subclass events.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            try:
                await handler.handle(event)
            except Exception:
                _logger.exception(
                    "Handler %s failed for event %s",
                    handler.__class__.__name__,
                    event_type.__name__,
                )


__all__ = ["InProcessEventBus"]
