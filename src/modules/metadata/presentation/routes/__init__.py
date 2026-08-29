"""Metadata API routes."""

from src.modules.metadata.presentation.routes.artwork_routes import router as artwork_router
from src.modules.metadata.presentation.routes.person_bio_routes import (
    router as person_bio_router,
)

__all__ = ["artwork_router", "person_bio_router"]
