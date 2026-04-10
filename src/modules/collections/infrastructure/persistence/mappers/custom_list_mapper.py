"""Mapper between CustomList/CustomListItem entities and ORM models."""

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.value_objects import CustomListItemId, ListId
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
)
from src.shared_kernel.value_objects import CollectionMediaType


class CustomListMapper:
    """Bidirectional mapper between CustomList entity and ORM model.

    Example:
        >>> model = CustomListMapper.to_model(entity)
        >>> entity = CustomListMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: CustomList) -> CustomListModel:
        """Convert CustomList entity to ORM model.

        Args:
            entity: The domain entity.

        Returns:
            SQLAlchemy model ready for persistence.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return CustomListModel(
            external_id=str(entity.id),
            name=entity.name.value,
            item_count=entity.item_count,
        )

    @staticmethod
    def to_entity(model: CustomListModel) -> CustomList:
        """Convert ORM model to CustomList entity.

        Args:
            model: The SQLAlchemy model.

        Returns:
            Domain CustomList entity.
        """
        return CustomList(
            id=ListId(model.external_id),
            name=model.name,
            item_count=model.item_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: CustomListModel, entity: CustomList) -> CustomListModel:
        """Update existing ORM model with entity data.

        Args:
            model: The existing model.
            entity: The updated entity.

        Returns:
            The updated model.
        """
        model.name = entity.name.value
        model.item_count = entity.item_count
        return model


class CustomListItemMapper:
    """Bidirectional mapper between CustomListItem entity and ORM model.

    Example:
        >>> model = CustomListItemMapper.to_model(entity, list_internal_id=1)
        >>> entity = CustomListItemMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: CustomListItem, list_internal_id: int) -> CustomListItemModel:
        """Convert CustomListItem entity to ORM model.

        Args:
            entity: The domain entity.
            list_internal_id: Internal DB ID of the parent custom list.

        Returns:
            SQLAlchemy model ready for persistence.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return CustomListItemModel(
            external_id=str(entity.id),
            custom_list_id=list_internal_id,
            media_id=entity.media_id,
            media_type=entity.media_type,
            position=entity.position,
            added_at=entity.added_at,
        )

    @staticmethod
    def to_entity(model: CustomListItemModel) -> CustomListItem:
        """Convert ORM model to CustomListItem entity.

        Args:
            model: The SQLAlchemy model.

        Returns:
            Domain CustomListItem entity.
        """
        return CustomListItem(
            id=CustomListItemId(model.external_id),
            media_id=model.media_id,
            media_type=CollectionMediaType(model.media_type),
            position=model.position,
            added_at=model.added_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = ["CustomListItemMapper", "CustomListMapper"]
