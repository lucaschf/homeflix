"""Media API routes."""

from src.modules.media.presentation.routes.enrichment_routes import router as enrichment_router
from src.modules.media.presentation.routes.featured_routes import router as featured_router
from src.modules.media.presentation.routes.movie_routes import router as movie_router
from src.modules.media.presentation.routes.scan_routes import router as scan_router
from src.modules.media.presentation.routes.series_routes import router as series_router
from src.modules.media.presentation.routes.stream_routes import router as stream_router

__all__ = [
    "enrichment_router",
    "featured_router",
    "movie_router",
    "scan_router",
    "series_router",
    "stream_router",
]
