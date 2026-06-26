"""Mapper between CustomList/CustomListItem entities and ORM models."""

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.value_objects import (
    CollectionMediaId,
    CustomListItemId,
    ListId,
)
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId


class CustomListMapper:
    """Bidirectional mapper between CustomList entity and ORM model."""

    @staticmethod
    def to_model(entity: CustomList) -> CustomListModel:
        """Convert CustomList entity to ORM model."""
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return CustomListModel(
            external_id=str(entity.id),
            profile_id=str(entity.profile_id),
            name=entity.name.value,
            description=entity.description,
            item_count=entity.item_count,
        )

    @staticmethod
    def to_entity(model: CustomListModel) -> CustomList:
        """Convert ORM model to CustomList entity."""
        return CustomList(
            id=ListId(model.external_id),
            profile_id=ProfileId(model.profile_id),
            name=model.name,
            description=model.description,
            item_count=model.item_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: CustomListModel, entity: CustomList) -> CustomListModel:
        """Update mutable fields. ``profile_id`` is intentionally not touched."""
        model.name = entity.name.value
        model.description = entity.description
        model.item_count = entity.item_count
        return model


class CustomListItemMapper:
    """Bidirectional mapper between CustomListItem entity and ORM model."""

    @staticmethod
    def to_model(entity: CustomListItem, list_internal_id: int) -> CustomListItemModel:
        """Convert CustomListItem entity to ORM model."""
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return CustomListItemModel(
            external_id=str(entity.id),
            custom_list_id=list_internal_id,
            media_id=entity.media_id.value,
            media_type=entity.media_type,
            position=entity.position,
            added_at=entity.added_at,
        )

    @staticmethod
    def to_entity(model: CustomListItemModel) -> CustomListItem:
        """Convert ORM model to CustomListItem entity."""
        return CustomListItem(
            id=CustomListItemId(model.external_id),
            media_id=CollectionMediaId(model.media_id),
            media_type=MediaType(model.media_type),
            position=model.position,
            added_at=model.added_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = ["CustomListItemMapper", "CustomListMapper"]
