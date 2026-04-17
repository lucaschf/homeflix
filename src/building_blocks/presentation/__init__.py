"""Shared presentation-layer building blocks.

Provides framework-agnostic helpers that every bounded context reuses
at the HTTP boundary: the API Response Envelope (v3.0 standard),
global exception-to-HTTP translation, and per-request context middleware.

The building_blocks package stays free of business logic; these helpers
exist to keep route handlers thin and responses consistent across
modules.
"""

from src.building_blocks.presentation.request_context import (
    RequestContextMiddleware,
    get_current_request_id,
)
from src.building_blocks.presentation.responses import (
    Pagination,
    api_list,
    api_single,
)

__all__ = [
    "Pagination",
    "RequestContextMiddleware",
    "api_list",
    "api_single",
    "get_current_request_id",
]
