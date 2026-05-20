"""Cross-BC event handlers for the Catalog Requests bounded context."""

from src.modules.catalog_requests.application.event_handlers.on_media_enriched import (
    OnMediaEnrichedHandler,
)

__all__ = ["OnMediaEnrichedHandler"]
