"""Catalog Requests repository implementations."""

from src.modules.catalog_requests.infrastructure.persistence.repositories.catalog_request_repository import (
    SQLAlchemyCatalogRequestRepository,
)

__all__ = ["SQLAlchemyCatalogRequestRepository"]
