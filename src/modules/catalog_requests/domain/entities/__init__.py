"""Catalog Requests domain entities."""

from src.modules.catalog_requests.domain.entities.catalog_request import CatalogRequest
from src.modules.catalog_requests.domain.entities.catalog_subscription import (
    CatalogSubscription,
)

__all__ = ["CatalogRequest", "CatalogSubscription"]
