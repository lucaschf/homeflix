"""Mapper between ``CatalogRequest`` entity and ``CatalogRequestModel``."""

from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    CatalogRequestSource,
)
from src.modules.catalog_requests.infrastructure.persistence.models import (
    CatalogRequestModel,
)
from src.shared_kernel.value_objects import MediaType


class CatalogRequestMapper:
    """Bidirectional mapper between domain aggregate and ORM model.

    Example:
        >>> model = CatalogRequestMapper.to_model(entity)
        >>> entity = CatalogRequestMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: CatalogRequest) -> CatalogRequestModel:
        """Convert ``CatalogRequest`` entity to ORM model.

        Args:
            entity: The domain aggregate. Must have an ``id``.

        Returns:
            SQLAlchemy model ready for persistence.

        Raises:
            ValueError: When ``entity.id`` is ``None``.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return CatalogRequestModel(
            external_id=str(entity.id),
            tmdb_id=entity.tmdb_id,
            media_type=entity.media_type.value,
            title=entity.title,
            requester_user_id=entity.requester_user_id,
            collection_tmdb_id=entity.collection_tmdb_id,
            source=entity.source.value,
            notify_on_arrival=entity.notify_on_arrival,
            requested_at=entity.requested_at,
            fulfilled_at=entity.fulfilled_at,
        )

    @staticmethod
    def to_entity(model: CatalogRequestModel) -> CatalogRequest:
        """Convert ORM model to domain aggregate."""
        return CatalogRequest(
            id=CatalogRequestId(model.external_id),
            tmdb_id=model.tmdb_id,
            media_type=MediaType(model.media_type),
            title=model.title,
            requester_user_id=model.requester_user_id,
            collection_tmdb_id=model.collection_tmdb_id,
            source=CatalogRequestSource(model.source),
            notify_on_arrival=model.notify_on_arrival,
            requested_at=model.requested_at,
            fulfilled_at=model.fulfilled_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(
        model: CatalogRequestModel,
        entity: CatalogRequest,
    ) -> CatalogRequestModel:
        """Update an existing ORM model with entity data.

        Only mutable fields are written back: ``tmdb_id`` /
        ``media_type`` are part of the natural key and never change
        after creation, so updating them would be a bug. ``title``
        and ``requester_user_id`` are mutable so a re-submit from
        a client that finally knows the title (or comes from a
        different user) can backfill the snapshot / replace the
        recipient on legacy rows.
        """
        model.title = entity.title
        model.requester_user_id = entity.requester_user_id
        model.collection_tmdb_id = entity.collection_tmdb_id
        model.notify_on_arrival = entity.notify_on_arrival
        model.fulfilled_at = entity.fulfilled_at
        return model


__all__ = ["CatalogRequestMapper"]
