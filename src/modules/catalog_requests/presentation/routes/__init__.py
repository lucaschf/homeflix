"""Catalog Requests REST routes."""

from src.modules.catalog_requests.presentation.routes.admin_catalog_request_routes import (
    router as admin_catalog_request_router,
)
from src.modules.catalog_requests.presentation.routes.catalog_request_routes import (
    router as catalog_request_router,
)

__all__ = ["admin_catalog_request_router", "catalog_request_router"]
