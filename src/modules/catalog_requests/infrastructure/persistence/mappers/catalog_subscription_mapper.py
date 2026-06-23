"""Mapper between ``CatalogSubscription`` entity and ``CatalogSubscriptionModel``."""

from src.modules.catalog_requests.domain.entities import CatalogSubscription
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    CatalogSubscriptionId,
)
from src.modules.catalog_requests.infrastructure.persistence.models import (
    CatalogSubscriptionModel,
)


class CatalogSubscriptionMapper:
    """Bidirectional mapper between domain aggregate and ORM model.

    There is no ``update_model``: a subscription is immutable once
    created — it is added or soft-deleted (unsubscribe), never
    mutated.

    Example:
        >>> model = CatalogSubscriptionMapper.to_model(entity)
        >>> entity = CatalogSubscriptionMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: CatalogSubscription) -> CatalogSubscriptionModel:
        """Convert ``CatalogSubscription`` entity to ORM model.

        ``created_at`` is left to the DB server default (the inherited
        base timestamp), matching ``CatalogRequestMapper``.

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

        return CatalogSubscriptionModel(
            external_id=str(entity.id),
            request_id=str(entity.request_id),
            user_id=entity.user_id,
        )

    @staticmethod
    def to_entity(model: CatalogSubscriptionModel) -> CatalogSubscription:
        """Convert ORM model to domain aggregate."""
        return CatalogSubscription(
            id=CatalogSubscriptionId(model.external_id),
            request_id=CatalogRequestId(model.request_id),
            user_id=model.user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = ["CatalogSubscriptionMapper"]
