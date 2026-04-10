"""Tests for ListId, CustomListItemId, and ListName value objects."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.collections.domain.value_objects import (
    CustomListItemId,
    ListId,
    ListName,
)


@pytest.mark.unit
class TestListIdCreation:
    """Tests for ListId generation and validation."""

    def test_should_generate_with_lst_prefix(self) -> None:
        list_id = ListId.generate()

        assert list_id.prefix == "lst"
        assert str(list_id).startswith("lst_")

    def test_should_have_12_char_random_part(self) -> None:
        list_id = ListId.generate()

        assert len(list_id.random_part) == 12

    def test_should_generate_unique_ids(self) -> None:
        ids = {ListId.generate() for _ in range(100)}

        assert len(ids) == 100

    def test_should_accept_valid_id_string(self) -> None:
        list_id = ListId("lst_abc123def456")

        assert list_id.value == "lst_abc123def456"

    def test_should_reject_wrong_prefix(self) -> None:
        with pytest.raises(DomainValidationException, match="must have 'lst' prefix"):
            ListId("mov_abc123def456")

    def test_should_reject_missing_underscore(self) -> None:
        with pytest.raises(DomainValidationException, match="must contain underscore"):
            ListId("lstabc123def456")

    def test_should_reject_wrong_length_random_part(self) -> None:
        with pytest.raises(DomainValidationException, match="12 characters"):
            ListId("lst_short")

    def test_should_reject_non_string(self) -> None:
        with pytest.raises(DomainValidationException, match="must be a string"):
            ListId(12345)  # type: ignore[arg-type]


@pytest.mark.unit
class TestListIdEquality:
    """Tests for ListId equality and hashing."""

    def test_should_be_equal_with_same_value(self) -> None:
        id_a = ListId("lst_abc123def456")
        id_b = ListId("lst_abc123def456")

        assert id_a == id_b

    def test_should_not_be_equal_with_different_value(self) -> None:
        id_a = ListId.generate()
        id_b = ListId.generate()

        assert id_a != id_b

    def test_should_be_usable_in_sets(self) -> None:
        list_id = ListId("lst_abc123def456")
        id_set = {list_id, ListId("lst_abc123def456")}

        assert len(id_set) == 1

    def test_should_be_usable_as_dict_key(self) -> None:
        list_id = ListId("lst_abc123def456")
        mapping = {list_id: "test"}

        assert mapping[ListId("lst_abc123def456")] == "test"


@pytest.mark.unit
class TestListIdGenerateIfAbsent:
    """Tests for ListId.generate_if_absent()."""

    def test_should_return_existing_id(self) -> None:
        existing = ListId.generate()
        result = ListId.generate_if_absent(existing)

        assert result == existing

    def test_should_generate_new_when_none(self) -> None:
        result = ListId.generate_if_absent(None)

        assert result is not None
        assert result.prefix == "lst"


@pytest.mark.unit
class TestCustomListItemIdCreation:
    """Tests for CustomListItemId generation and validation."""

    def test_should_generate_with_cli_prefix(self) -> None:
        item_id = CustomListItemId.generate()

        assert item_id.prefix == "cli"
        assert str(item_id).startswith("cli_")

    def test_should_have_12_char_random_part(self) -> None:
        item_id = CustomListItemId.generate()

        assert len(item_id.random_part) == 12

    def test_should_accept_valid_id_string(self) -> None:
        item_id = CustomListItemId("cli_abc123def456")

        assert item_id.value == "cli_abc123def456"

    def test_should_reject_wrong_prefix(self) -> None:
        with pytest.raises(DomainValidationException, match="must have 'cli' prefix"):
            CustomListItemId("lst_abc123def456")

    def test_should_generate_unique_ids(self) -> None:
        ids = {CustomListItemId.generate() for _ in range(100)}

        assert len(ids) == 100


@pytest.mark.unit
class TestListNameCreation:
    """Tests for ListName value object."""

    def test_should_create_with_valid_name(self) -> None:
        name = ListName("Action Movies")

        assert name.value == "Action Movies"

    def test_should_strip_whitespace(self) -> None:
        name = ListName("  Sci-Fi Collection  ")

        assert name.value == "Sci-Fi Collection"

    def test_should_reject_empty_string(self) -> None:
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ListName("")

    def test_should_reject_whitespace_only(self) -> None:
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ListName("   ")

    def test_should_reject_name_exceeding_max_length(self) -> None:
        with pytest.raises(
            DomainValidationException,
            match=f"cannot exceed {ListName.MAX_LENGTH}",
        ):
            ListName("A" * (ListName.MAX_LENGTH + 1))

    def test_should_accept_name_at_max_length(self) -> None:
        name = ListName("A" * ListName.MAX_LENGTH)

        assert len(name.value) == ListName.MAX_LENGTH

    def test_should_reject_non_string(self) -> None:
        with pytest.raises(DomainValidationException, match="must be a string"):
            ListName(123)  # type: ignore[arg-type]


@pytest.mark.unit
class TestListNameEquality:
    """Tests for ListName equality."""

    def test_should_be_equal_with_same_value(self) -> None:
        name_a = ListName("Test")
        name_b = ListName("Test")

        assert name_a == name_b

    def test_should_not_be_equal_with_different_value(self) -> None:
        name_a = ListName("Test A")
        name_b = ListName("Test B")

        assert name_a != name_b
