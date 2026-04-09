"""Mapper between WatchlistItem entity and WatchlistItemModel."""

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.models import (
    WatchlistItemModel,
)
from src.shared_kernel.value_objects import CollectionMediaType


class WatchlistItemMapper:
    """Bidirectional mapper between WatchlistItem entity and ORM model.

    Example:
        >>> model = WatchlistItemMapper.to_model(entity)
        >>> entity = WatchlistItemMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: WatchlistItem) -> WatchlistItemModel:
        """Convert WatchlistItem entity to ORM model.

        Args:
            entity: The domain entity.

        Returns:
            SQLAlchemy model ready for persistence.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return WatchlistItemModel(
            external_id=str(entity.id),
            media_id=entity.media_id,
            media_type=entity.media_type,
            added_at=entity.added_at,
        )

    @staticmethod
    def to_entity(model: WatchlistItemModel) -> WatchlistItem:
        """Convert ORM model to WatchlistItem entity.

        Args:
            model: The SQLAlchemy model.

        Returns:
            Domain WatchlistItem entity.
        """
        return WatchlistItem(
            id=ListId(model.external_id),
            media_id=model.media_id,
            media_type=CollectionMediaType(model.media_type),
            added_at=model.added_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: WatchlistItemModel, entity: WatchlistItem) -> WatchlistItemModel:
        """Update existing ORM model with entity data.

        Args:
            model: The existing model.
            entity: The updated entity.

        Returns:
            The updated model.
        """
        model.media_id = entity.media_id
        model.media_type = entity.media_type
        model.added_at = entity.added_at
        return model


__all__ = ["WatchlistItemMapper"]
