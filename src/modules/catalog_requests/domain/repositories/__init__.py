"""Catalog Requests domain repositories."""

from src.modules.catalog_requests.domain.repositories.catalog_request_repository import (
    CatalogRequestRepository,
)
from src.modules.catalog_requests.domain.repositories.catalog_subscription_repository import (
    CatalogSubscriptionRepository,
)

__all__ = ["CatalogRequestRepository", "CatalogSubscriptionRepository"]
