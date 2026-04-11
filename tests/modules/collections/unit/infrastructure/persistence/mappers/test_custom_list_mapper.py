"""Unit tests for CustomListMapper and CustomListItemMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.value_objects import CustomListItemId, ListId
from src.modules.collections.infrastructure.persistence.mappers import (
    CustomListItemMapper,
    CustomListMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
)
from src.shared_kernel.value_objects import CollectionMediaType


@pytest.mark.unit
class TestCustomListMapper:
    """Tests for CustomListMapper."""

    def test_to_model_should_raise_when_id_is_none(self) -> None:
        custom_list = CustomList(name="Test")

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            CustomListMapper.to_model(custom_list)

    def test_to_model_should_convert_entity_correctly(self) -> None:
        list_id = ListId.generate()
        custom_list = CustomList(id=list_id, name="Action Movies", item_count=5)

        model = CustomListMapper.to_model(custom_list)

        assert model.external_id == str(list_id)
        assert model.name == "Action Movies"
        assert model.item_count == 5

    def test_to_entity_should_convert_model_correctly(self) -> None:
        list_id = ListId.generate()
        now = datetime.now(UTC)
        model = CustomListModel(
            external_id=str(list_id),
            name="Comedy",
            item_count=3,
        )
        model.created_at = now
        model.updated_at = now

        entity = CustomListMapper.to_entity(model)

        assert entity.id == list_id
        assert entity.name.value == "Comedy"
        assert entity.item_count == 3
        assert entity.created_at == now
        assert entity.updated_at == now

    def test_round_trip_should_preserve_fields(self) -> None:
        list_id = ListId.generate()
        original = CustomList(id=list_id, name="Sci-Fi", item_count=2)
        model = CustomListMapper.to_model(original)
        model.created_at = original.created_at
        model.updated_at = original.updated_at

        result = CustomListMapper.to_entity(model)

        assert result.id == original.id
        assert result.name == original.name
        assert result.item_count == original.item_count

    def test_update_model_should_update_fields(self) -> None:
        list_id = ListId.generate()
        model = CustomListModel(
            external_id=str(list_id),
            name="Old Name",
            item_count=1,
        )
        updated = CustomList(id=list_id, name="New Name", item_count=5)

        result = CustomListMapper.update_model(model, updated)

        assert result.name == "New Name"
        assert result.item_count == 5


@pytest.mark.unit
class TestCustomListItemMapper:
    """Tests for CustomListItemMapper."""

    def test_to_model_should_raise_when_id_is_none(self) -> None:
        item = CustomListItem(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            CustomListItemMapper.to_model(item, list_internal_id=1)

    def test_to_model_should_convert_entity_correctly(self) -> None:
        item_id = CustomListItemId.generate()
        added_at = datetime.now(UTC)
        item = CustomListItem(
            id=item_id,
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
            position=2,
            added_at=added_at,
        )

        model = CustomListItemMapper.to_model(item, list_internal_id=42)

        assert model.external_id == str(item_id)
        assert model.custom_list_id == 42
        assert model.media_id == "mov_abc123def456"
        assert model.media_type == CollectionMediaType.MOVIE
        assert model.position == 2
        assert model.added_at == added_at

    def test_to_entity_should_convert_model_correctly(self) -> None:
        item_id = CustomListItemId.generate()
        added_at = datetime.now(UTC)
        now = datetime.now(UTC)
        model = CustomListItemModel(
            external_id=str(item_id),
            custom_list_id=1,
            media_id="ser_xyz789abc123",
            media_type="series",
            position=0,
            added_at=added_at,
        )
        model.created_at = now
        model.updated_at = now

        entity = CustomListItemMapper.to_entity(model)

        assert entity.id == item_id
        assert entity.media_id == "ser_xyz789abc123"
        assert entity.media_type == CollectionMediaType.SERIES
        assert entity.position == 0
        assert entity.added_at == added_at
