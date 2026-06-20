"""Media API routes."""

from src.modules.media.presentation.routes.admin_conflicts_routes import (
    router as admin_conflicts_router,
)
from src.modules.media.presentation.routes.admin_credits_routes import (
    router as admin_credits_router,
)
from src.modules.media.presentation.routes.admin_intro_detection_routes import (
    router as admin_intro_detection_router,
)
from src.modules.media.presentation.routes.admin_jobs_routes import (
    router as admin_jobs_router,
)
from src.modules.media.presentation.routes.admin_overview_routes import (
    router as admin_overview_router,
)
from src.modules.media.presentation.routes.admin_relink_routes import (
    router as admin_relink_router,
)
from src.modules.media.presentation.routes.admin_scan_routes import (
    router as admin_scan_router,
)
from src.modules.media.presentation.routes.admin_system_routes import (
    router as admin_system_router,
)
from src.modules.media.presentation.routes.catalog_routes import router as catalog_router
from src.modules.media.presentation.routes.collection_routes import router as collection_router
from src.modules.media.presentation.routes.enrichment_routes import router as enrichment_router
from src.modules.media.presentation.routes.featured_routes import router as featured_router
from src.modules.media.presentation.routes.movie_routes import router as movie_router
from src.modules.media.presentation.routes.people_routes import router as people_router
from src.modules.media.presentation.routes.scan_routes import router as scan_router
from src.modules.media.presentation.routes.search_routes import router as search_router
from src.modules.media.presentation.routes.series_routes import router as series_router
from src.modules.media.presentation.routes.stream_routes import router as stream_router
from src.modules.media.presentation.routes.tmdb_lookup_routes import (
    router as tmdb_lookup_router,
)

__all__ = [
    "admin_conflicts_router",
    "admin_credits_router",
    "admin_intro_detection_router",
    "admin_jobs_router",
    "admin_overview_router",
    "admin_relink_router",
    "admin_scan_router",
    "admin_system_router",
    "catalog_router",
    "collection_router",
    "enrichment_router",
    "featured_router",
    "movie_router",
    "people_router",
    "scan_router",
    "search_router",
    "series_router",
    "stream_router",
    "tmdb_lookup_router",
]
