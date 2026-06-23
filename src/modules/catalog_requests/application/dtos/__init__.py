"""Catalog Requests application DTOs."""

from src.modules.catalog_requests.application.dtos.catalog_request_dtos import (
    CatalogRequestOutput,
    CreateCatalogRequestInput,
    DismissCatalogRequestInput,
    SubscribeCatalogNotificationInput,
    UnsubscribeCatalogNotificationInput,
)

__all__ = [
    "CatalogRequestOutput",
    "CreateCatalogRequestInput",
    "DismissCatalogRequestInput",
    "SubscribeCatalogNotificationInput",
    "UnsubscribeCatalogNotificationInput",
]
