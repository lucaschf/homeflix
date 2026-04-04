"""Media API routes."""

from src.modules.media.presentation.routes.movie_routes import router as movie_router
from src.modules.media.presentation.routes.scan_routes import router as scan_router
from src.modules.media.presentation.routes.series_routes import router as series_router

__all__ = ["movie_router", "scan_router", "series_router"]
