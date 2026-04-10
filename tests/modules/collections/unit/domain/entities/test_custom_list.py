"""Tests for CustomList aggregate root and CustomListItem entity."""

import pytest

from src.building_blocks.domain import BusinessRuleViolationException
from src.building_blocks.domain.errors import DomainValidationException
from src.modules.collections.domain.entities import (
    MAX_ITEMS_PER_LIST,
    CustomList,
    CustomListItem,
)
from src.modules.collections.domain.value_objects import (
    CustomListItemId,
    ListId,
    ListName,
)
from src.shared_kernel.value_objects import CollectionMediaType


@pytest.mark.unit
class TestCustomListCreation:
    """Tests for CustomList instantiation."""

    def test_should_create_with_required_fields(self) -> None:
        custom_list = CustomList(name="Action Movies")

        assert custom_list.id is None
        assert custom_list.name == ListName("Action Movies")
        assert custom_list.name.value == "Action Movies"
        assert custom_list.item_count == 0

    def test_should_create_via_factory_with_auto_id(self) -> None:
        custom_list = CustomList.create(name="Action Movies")

        assert custom_list.id is not None
        assert isinstance(custom_list.id, ListId)
        assert custom_list.id.prefix == "lst"

    def test_factory_should_strip_name_whitespace(self) -> None:
        custom_list = CustomList.create(name="  Action Movies  ")

        assert custom_list.name.value == "Action Movies"

    def test_factory_should_initialize_item_count_to_zero(self) -> None:
        custom_list = CustomList.create(name="My List")

        assert custom_list.item_count == 0

    def test_should_accept_string_id_and_convert(self) -> None:
        list_id = ListId.generate()
        custom_list = CustomList(id=list_id, name="Test")

        assert custom_list.id == list_id

    def test_should_be_frozen(self) -> None:
        custom_list = CustomList.create(name="Test")

        with pytest.raises(DomainValidationException):
            custom_list.name = "New Name"  # type: ignore[misc, assignment]

    def test_should_have_timestamps(self) -> None:
        custom_list = CustomList.create(name="Test")

        assert custom_list.created_at is not None
        assert custom_list.updated_at is not None


@pytest.mark.unit
class TestCustomListRename:
    """Tests for CustomList.rename()."""

    def test_should_return_new_instance_with_updated_name(self) -> None:
        original = CustomList.create(name="Old Name")
        renamed = original.rename("New Name")

        assert renamed.name.value == "New Name"
        assert original.name.value == "Old Name"

    def test_should_preserve_id(self) -> None:
        original = CustomList.create(name="Old Name")
        renamed = original.rename("New Name")

        assert renamed.id == original.id

    def test_should_strip_new_name_whitespace(self) -> None:
        custom_list = CustomList.create(name="Original")
        renamed = custom_list.rename("  Renamed  ")

        assert renamed.name.value == "Renamed"

    def test_should_preserve_item_count(self) -> None:
        custom_list = CustomList.create(name="Original")
        incremented = custom_list.increment_item_count()
        renamed = incremented.rename("Renamed")

        assert renamed.item_count == 1


@pytest.mark.unit
class TestCustomListItemCount:
    """Tests for increment/decrement item count."""

    def test_should_increment_item_count(self) -> None:
        custom_list = CustomList.create(name="Test")
        updated = custom_list.increment_item_count()

        assert updated.item_count == 1
        assert custom_list.item_count == 0

    def test_should_increment_multiple_times(self) -> None:
        custom_list = CustomList.create(name="Test")
        updated = custom_list.increment_item_count()
        updated = updated.increment_item_count()
        updated = updated.increment_item_count()

        assert updated.item_count == 3

    def test_should_raise_when_exceeding_max_items(self) -> None:
        custom_list = CustomList(
            id=ListId.generate(),
            name="Full List",
            item_count=MAX_ITEMS_PER_LIST,
        )

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            custom_list.increment_item_count()

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_LIMIT_EXCEEDED"

    def test_should_allow_increment_at_max_minus_one(self) -> None:
        custom_list = CustomList(
            id=ListId.generate(),
            name="Almost Full",
            item_count=MAX_ITEMS_PER_LIST - 1,
        )

        updated = custom_list.increment_item_count()

        assert updated.item_count == MAX_ITEMS_PER_LIST

    def test_should_decrement_item_count(self) -> None:
        custom_list = CustomList(
            id=ListId.generate(),
            name="Test",
            item_count=5,
        )
        updated = custom_list.decrement_item_count()

        assert updated.item_count == 4

    def test_should_not_go_below_zero_on_decrement(self) -> None:
        custom_list = CustomList.create(name="Test")
        updated = custom_list.decrement_item_count()

        assert updated.item_count == 0


@pytest.mark.unit
class TestCustomListEquality:
    """Tests for CustomList equality and hashing."""

    def test_should_be_equal_by_id(self) -> None:
        list_id = ListId.generate()
        list_a = CustomList(id=list_id, name="A")
        list_b = CustomList(id=list_id, name="B")

        assert list_a == list_b

    def test_should_not_be_equal_with_different_ids(self) -> None:
        list_a = CustomList.create(name="A")
        list_b = CustomList.create(name="A")

        assert list_a != list_b

    def test_should_not_be_equal_when_id_is_none(self) -> None:
        list_a = CustomList(name="A")
        list_b = CustomList(name="A")

        assert list_a != list_b

    def test_should_be_hashable(self) -> None:
        custom_list = CustomList.create(name="Test")

        assert hash(custom_list) is not None
        assert {custom_list}


@pytest.mark.unit
class TestCustomListItemCreation:
    """Tests for CustomListItem entity."""

    def test_should_create_with_required_fields(self) -> None:
        item = CustomListItem(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.id is None
        assert item.media_id == "mov_abc123def456"
        assert item.media_type == CollectionMediaType.MOVIE
        assert item.position == 0

    def test_should_create_via_factory_with_auto_id(self) -> None:
        item = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.id is not None
        assert isinstance(item.id, CustomListItemId)
        assert item.id.prefix == "cli"

    def test_should_create_with_custom_position(self) -> None:
        item = CustomListItem.create(
            media_id="ser_abc123def456",
            media_type=CollectionMediaType.SERIES,
            position=5,
        )

        assert item.position == 5

    def test_should_have_added_at_timestamp(self) -> None:
        item = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.added_at is not None

    def test_should_accept_series_media_type(self) -> None:
        item = CustomListItem.create(
            media_id="ser_abc123def456",
            media_type=CollectionMediaType.SERIES,
        )

        assert item.media_type == CollectionMediaType.SERIES

    def test_should_be_frozen(self) -> None:
        item = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        with pytest.raises(DomainValidationException):
            item.position = 10  # type: ignore[misc]
