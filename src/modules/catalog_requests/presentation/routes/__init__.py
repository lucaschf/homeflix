"""Catalog Requests REST routes."""

from src.modules.catalog_requests.presentation.routes.catalog_request_routes import (
    router as catalog_request_router,
)

__all__ = ["catalog_request_router"]
