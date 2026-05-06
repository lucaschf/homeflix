"""Tests for InProcessEventBus."""

from dataclasses import dataclass

import pytest

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.building_blocks.infrastructure.in_process_event_bus import InProcessEventBus


@dataclass(frozen=True)
class FakeEvent(DomainEvent):
    """Test domain event."""

    payload: str = ""


@dataclass(frozen=True)
class OtherEvent(DomainEvent):
    """A different test event."""

    value: int = 0


class RecordingHandler(EventHandler):
    """Handler that records all received events."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def handle(self, event: DomainEvent) -> None:
        self.events.append(event)


class FailingHandler(EventHandler):
    """Handler that always raises."""

    def __init__(self) -> None:
        self.call_count = 0

    async def handle(self, event: DomainEvent) -> None:
        self.call_count += 1
        raise RuntimeError("Handler failed intentionally")


@pytest.mark.unit
class TestInProcessEventBusSubscribe:
    """Tests for subscribe observed through publish behavior."""

    @pytest.mark.asyncio
    async def test_subscribed_handler_should_receive_published_event(self) -> None:
        bus = InProcessEventBus()
        handler = RecordingHandler()

        bus.subscribe(FakeEvent, handler)
        await bus.publish(FakeEvent(payload="hello"))

        assert len(handler.events) == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers_should_all_be_invoked(self) -> None:
        bus = InProcessEventBus()
        h1 = RecordingHandler()
        h2 = RecordingHandler()

        bus.subscribe(FakeEvent, h1)
        bus.subscribe(FakeEvent, h2)
        await bus.publish(FakeEvent())

        assert len(h1.events) == 1
        assert len(h2.events) == 1

    @pytest.mark.asyncio
    async def test_duplicate_subscription_should_invoke_handler_twice(self) -> None:
        bus = InProcessEventBus()
        handler = RecordingHandler()

        bus.subscribe(FakeEvent, handler)
        bus.subscribe(FakeEvent, handler)
        await bus.publish(FakeEvent())

        # Duplicate subscription is not deduped
        assert len(handler.events) == 2

    @pytest.mark.asyncio
    async def test_handlers_for_different_event_types_should_be_isolated(self) -> None:
        bus = InProcessEventBus()
        fake_handler = RecordingHandler()
        other_handler = RecordingHandler()

        bus.subscribe(FakeEvent, fake_handler)
        bus.subscribe(OtherEvent, other_handler)
        await bus.publish(FakeEvent())

        assert len(fake_handler.events) == 1
        assert len(other_handler.events) == 0

        await bus.publish(OtherEvent())

        assert len(fake_handler.events) == 1
        assert len(other_handler.events) == 1


@pytest.mark.unit
class TestInProcessEventBusPublish:
    """Tests for publish semantics beyond basic routing."""

    @pytest.mark.asyncio
    async def test_should_preserve_event_identity(self) -> None:
        bus = InProcessEventBus()
        handler = RecordingHandler()
        bus.subscribe(FakeEvent, handler)
        event = FakeEvent(payload="hello")

        await bus.publish(event)

        assert handler.events[0] is event

    @pytest.mark.asyncio
    async def test_should_isolate_handler_failures(self) -> None:
        bus = InProcessEventBus()
        failing = FailingHandler()
        recording = RecordingHandler()
        bus.subscribe(FakeEvent, failing)
        bus.subscribe(FakeEvent, recording)

        # Should not raise — failure is logged and swallowed
        await bus.publish(FakeEvent(payload="test"))

        assert failing.call_count == 1
        assert len(recording.events) == 1

    @pytest.mark.asyncio
    async def test_should_not_raise_when_no_handlers(self) -> None:
        bus = InProcessEventBus()
        # Should not raise even with no handlers registered
        await bus.publish(FakeEvent(payload="ignored"))

    @pytest.mark.asyncio
    async def test_should_invoke_handlers_in_subscription_order(self) -> None:
        bus = InProcessEventBus()
        call_order: list[str] = []

        class OrderedHandler(EventHandler):
            def __init__(self, name: str) -> None:
                self.name = name

            async def handle(self, event: DomainEvent) -> None:
                call_order.append(self.name)

        bus.subscribe(FakeEvent, OrderedHandler("first"))
        bus.subscribe(FakeEvent, OrderedHandler("second"))
        bus.subscribe(FakeEvent, OrderedHandler("third"))

        await bus.publish(FakeEvent())

        assert call_order == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_should_use_exact_type_matching_not_inheritance(self) -> None:
        """Handlers registered for a base class do not receive subclass events."""

        @dataclass(frozen=True)
        class ChildEvent(FakeEvent):
            extra: str = ""

        bus = InProcessEventBus()
        base_handler = RecordingHandler()
        child_handler = RecordingHandler()
        bus.subscribe(FakeEvent, base_handler)
        bus.subscribe(ChildEvent, child_handler)

        await bus.publish(ChildEvent(payload="p", extra="e"))

        # Only the child handler receives the child event
        assert len(base_handler.events) == 0
        assert len(child_handler.events) == 1
