"""Mapper between WatchlistItem entity and WatchlistItemModel."""

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId, ListId
from src.modules.collections.infrastructure.persistence.models import (
    WatchlistItemModel,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId


class WatchlistItemMapper:
    """Bidirectional mapper between WatchlistItem entity and ORM model."""

    @staticmethod
    def to_model(entity: WatchlistItem) -> WatchlistItemModel:
        """Convert WatchlistItem entity to ORM model."""
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return WatchlistItemModel(
            external_id=str(entity.id),
            profile_id=str(entity.profile_id),
            media_id=entity.media_id.value,
            media_type=entity.media_type,
            added_at=entity.added_at,
        )

    @staticmethod
    def to_entity(model: WatchlistItemModel) -> WatchlistItem:
        """Convert ORM model to WatchlistItem entity."""
        return WatchlistItem(
            id=ListId(model.external_id),
            profile_id=ProfileId(model.profile_id),
            media_id=CollectionMediaId(model.media_id),
            media_type=MediaType(model.media_type),
            added_at=model.added_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(model: WatchlistItemModel, entity: WatchlistItem) -> WatchlistItemModel:
        """Refresh the mutable fields on restore (soft-delete reactivation).

        ``profile_id`` and ``media_id`` form the composite uniqueness
        key (``uq_watchlist_items_profile_media``); the caller used
        that pair to locate ``model`` in the first place, so any
        attempt to overwrite them here would either be a no-op or
        smuggle in a unique-constraint violation. ``media_type`` is
        a property of the media itself, not of the watchlist entry,
        and is also left untouched.
        """
        model.added_at = entity.added_at
        return model


__all__ = ["WatchlistItemMapper"]
