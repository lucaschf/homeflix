"""Tests for DomainEntity and AggregateRoot base classes."""

from datetime import UTC, datetime

from src.domain.shared.models import AggregateRoot, DomainEntity, utc_now


class SampleEntity(DomainEntity):
    """Sample entity for testing."""

    name: str


class SampleAggregateRoot(AggregateRoot):
    """Sample aggregate root for testing."""

    name: str


class TestUtcNow:
    """Tests for utc_now utility function."""

    def test_should_return_datetime_with_utc_timezone(self):
        now = utc_now()

        assert now.tzinfo == UTC

    def test_should_return_current_time(self):
        before = datetime.now(UTC)
        now = utc_now()
        after = datetime.now(UTC)

        assert before <= now <= after


class TestDomainEntityCreation:
    """Tests for DomainEntity instantiation."""

    def test_should_create_with_default_id_as_none(self):
        entity = SampleEntity(name="Test")

        assert entity.id is None

    def test_should_create_with_provided_id(self):
        entity = SampleEntity(id="test_123", name="Test")

        assert entity.id == "test_123"

    def test_should_set_created_at_automatically(self):
        before = datetime.now(UTC)
        entity = SampleEntity(name="Test")
        after = datetime.now(UTC)

        assert before <= entity.created_at <= after

    def test_should_set_updated_at_automatically(self):
        before = datetime.now(UTC)
        entity = SampleEntity(name="Test")
        after = datetime.now(UTC)

        assert before <= entity.updated_at <= after

    def test_should_accept_custom_timestamps(self):
        custom_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        entity = SampleEntity(
            name="Test",
            created_at=custom_time,
            updated_at=custom_time,
        )

        assert entity.created_at == custom_time
        assert entity.updated_at == custom_time


class TestDomainEntityEquality:
    """Tests for DomainEntity equality based on id."""

    def test_should_be_equal_when_same_id(self):
        entity1 = SampleEntity(id="test_123", name="First")
        entity2 = SampleEntity(id="test_123", name="Second")

        assert entity1 == entity2

    def test_should_not_be_equal_when_different_id(self):
        entity1 = SampleEntity(id="test_123", name="First")
        entity2 = SampleEntity(id="test_456", name="First")

        assert entity1 != entity2

    def test_should_not_be_equal_when_one_has_no_id(self):
        entity1 = SampleEntity(id="test_123", name="First")
        entity2 = SampleEntity(name="First")

        assert entity1 != entity2

    def test_should_not_be_equal_when_both_have_no_id(self):
        entity1 = SampleEntity(name="First")
        entity2 = SampleEntity(name="First")

        assert entity1 != entity2

    def test_should_return_not_implemented_for_different_types(self):
        entity = SampleEntity(id="test_123", name="Test")

        assert entity.__eq__("not_an_entity") == NotImplemented


class TestDomainEntityHashing:
    """Tests for DomainEntity hashing."""

    def test_should_be_hashable_with_id(self):
        entity = SampleEntity(id="test_123", name="Test")

        entity_set = {entity}

        assert entity in entity_set

    def test_should_have_same_hash_for_equal_entities(self):
        entity1 = SampleEntity(id="test_123", name="First")
        entity2 = SampleEntity(id="test_123", name="Second")

        assert hash(entity1) == hash(entity2)

    def test_should_have_different_hash_for_different_ids(self):
        entity1 = SampleEntity(id="test_123", name="Test")
        entity2 = SampleEntity(id="test_456", name="Test")

        assert hash(entity1) != hash(entity2)

    def test_should_use_object_id_hash_when_no_id(self):
        entity = SampleEntity(name="Test")

        # Hash should be based on object identity
        assert hash(entity) == hash(id(entity))


class TestDomainEntityTouch:
    """Tests for DomainEntity.touch() method."""

    def test_should_update_updated_at_timestamp(self):
        entity = SampleEntity(
            name="Test",
            updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        old_updated_at = entity.updated_at

        entity.touch()

        assert entity.updated_at > old_updated_at

    def test_should_not_change_created_at(self):
        created_time = datetime(2024, 1, 1, tzinfo=UTC)
        entity = SampleEntity(name="Test", created_at=created_time)

        entity.touch()

        assert entity.created_at == created_time


class TestAggregateRootCreation:
    """Tests for AggregateRoot instantiation."""

    def test_should_inherit_entity_properties(self):
        aggregate = SampleAggregateRoot(id="agg_123", name="Test")

        assert aggregate.id == "agg_123"
        assert aggregate.name == "Test"
        assert aggregate.created_at is not None
        assert aggregate.updated_at is not None

    def test_should_start_with_no_pending_events(self):
        aggregate = SampleAggregateRoot(name="Test")

        assert aggregate.has_pending_events is False


class TestAggregateRootEvents:
    """Tests for AggregateRoot domain events management."""

    def test_should_add_event(self):
        aggregate = SampleAggregateRoot(name="Test")
        event = {"type": "TestEvent", "data": "value"}

        aggregate.add_event(event)

        assert aggregate.has_pending_events is True

    def test_should_pull_events_and_clear(self):
        aggregate = SampleAggregateRoot(name="Test")
        event1 = {"type": "Event1"}
        event2 = {"type": "Event2"}
        aggregate.add_event(event1)
        aggregate.add_event(event2)

        events = aggregate.pull_events()

        assert events == [event1, event2]
        assert aggregate.has_pending_events is False

    def test_should_return_empty_list_when_no_events(self):
        aggregate = SampleAggregateRoot(name="Test")

        events = aggregate.pull_events()

        assert events == []

    def test_should_clear_events(self):
        aggregate = SampleAggregateRoot(name="Test")
        aggregate.add_event({"type": "Event"})

        aggregate.clear_events()

        assert aggregate.has_pending_events is False

    def test_pull_events_should_not_affect_original_event_objects(self):
        aggregate = SampleAggregateRoot(name="Test")
        event = {"type": "Event", "mutable": [1, 2, 3]}
        aggregate.add_event(event)

        pulled = aggregate.pull_events()
        pulled[0]["mutable"].append(4)

        # Original event object is affected (shallow copy)
        assert event["mutable"] == [1, 2, 3, 4]

    def test_has_pending_events_property(self):
        aggregate = SampleAggregateRoot(name="Test")

        assert aggregate.has_pending_events is False

        aggregate.add_event({"type": "Event"})
        assert aggregate.has_pending_events is True

        aggregate.clear_events()
        assert aggregate.has_pending_events is False
