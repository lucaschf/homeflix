"""Catalog Requests value objects."""

from src.modules.catalog_requests.domain.value_objects.catalog_request_id import (
    CatalogRequestId,
)
from src.modules.catalog_requests.domain.value_objects.requested_media_type import (
    RequestedMediaType,
)

__all__ = ["CatalogRequestId", "RequestedMediaType"]
