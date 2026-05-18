"""HomeFlix API Entry Point.

This is the main entry point for the FastAPI application.
It serves as the Composition Root where the DI container is configured.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.building_blocks.presentation import RequestContextMiddleware
from src.building_blocks.presentation.exception_handlers import register_exception_handlers
from src.config.containers import ApplicationContainer
from src.config.logging import get_logger, setup_logging
from src.config.settings import get_settings
from src.modules.catalog_requests.presentation.routes import (
    admin_catalog_request_router,
    catalog_request_router,
)
from src.modules.collections.presentation.routes import custom_list_router, watchlist_router
from src.modules.identity.infrastructure.auth import auth_backend, fastapi_users
from src.modules.identity.presentation.routes import (
    admin_user_router,
    profile_router,
    users_router,
)
from src.modules.library.presentation.routes.library_routes import (
    router as library_router,
)
from src.modules.media.presentation.routes import (
    admin_relink_router,
    admin_system_router,
    catalog_router,
    collection_router,
    enrichment_router,
    featured_router,
    movie_router,
    people_router,
    scan_router,
    search_router,
    series_router,
    stream_router,
)
from src.modules.preferences.presentation.routes.preferences_routes import (
    router as preferences_router,
)
from src.modules.watch_progress.presentation.routes import progress_router

#: Module paths whose ``@inject``-decorated callables are wired to the
#: dependency-injector container. Extracted as a module constant so e2e
#: tests can build a container with the same wiring without copying the
#: list (drift between the two would mean tests miss DI-resolved deps).
WIRED_ROUTE_MODULES: tuple[str, ...] = (
    "src.modules.media.presentation.routes.admin_relink_routes",
    "src.modules.media.presentation.routes.admin_system_routes",
    "src.modules.media.presentation.routes.catalog_routes",
    "src.modules.media.presentation.routes.collection_routes",
    "src.modules.media.presentation.routes.search_routes",
    "src.modules.media.presentation.routes.enrichment_routes",
    "src.modules.media.presentation.routes.featured_routes",
    "src.modules.media.presentation.routes.movie_routes",
    "src.modules.media.presentation.routes.people_routes",
    "src.modules.media.presentation.routes.scan_routes",
    "src.modules.media.presentation.routes.series_routes",
    "src.modules.media.presentation.routes.stream_routes",
    "src.modules.watch_progress.presentation.routes.progress_routes",
    "src.modules.collections.presentation.routes.watchlist_routes",
    "src.modules.collections.presentation.routes.custom_list_routes",
    "src.modules.catalog_requests.presentation.routes.catalog_request_routes",
    "src.modules.catalog_requests.presentation.routes.admin_catalog_request_routes",
    "src.modules.library.presentation.routes.library_routes",
    "src.modules.preferences.presentation.routes.preferences_routes",
    "src.modules.identity.presentation.routes.admin_user_routes",
    "src.modules.identity.presentation.routes.profile_routes",
    "src.modules.identity.presentation.routes.users_routes",
)


def create_container() -> ApplicationContainer:
    """Create and configure the DI container.

    Returns:
        Configured ApplicationContainer instance.
    """
    container = ApplicationContainer()
    # Wiring is configured per bounded context as they are implemented
    return container


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler.

    Handles startup and shutdown logic:
    - Startup: Initialize container, database connections
    - Shutdown: Close connections, cleanup resources
    """
    logger = get_logger()
    settings = get_settings()

    # Startup
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        environment=settings.app_env,
    )

    # Initialize DI container
    container = create_container()
    container.wire(modules=list(WIRED_ROUTE_MODULES))
    app.state.container = container

    # Initialize database
    await container.infrastructure.init_resources()

    # Subscribe domain event handlers
    _subscribe_event_handlers(container)

    # Start background scheduler (library scans + thumbnail backfill +
    # intro detection). The provider depends on the session_factory
    # Resource, so it resolves asynchronously — must be awaited. Always
    # pin a slot on app.state so the shutdown handler can do a single
    # truthy check.
    app.state.scheduler = None
    if settings.scheduler_enabled:
        scheduler = await container.library_scan_scheduler()
        await scheduler.start()
        if settings.thumbnail_backfill_enabled:
            backfill_job = await container.thumbnail_backfill_job()
            scheduler.add_interval_job(
                backfill_job.run,
                minutes=settings.thumbnail_backfill_interval_minutes,
                job_id="homeflix:thumbnail-backfill",
            )
        if settings.intro_detection_enabled:
            intro_job = await container.intro_detection_job()
            scheduler.add_interval_job(
                intro_job.run,
                minutes=settings.intro_detection_interval_minutes,
                job_id="homeflix:intro-detection",
            )
        app.state.scheduler = scheduler

    logger.info("Application ready")

    yield

    # Shutdown
    logger.info("Application shutting down")
    if app.state.scheduler:
        await app.state.scheduler.stop()
    await container.infrastructure.shutdown_resources()
    logger.info("Application stopped")


def _subscribe_event_handlers(container: ApplicationContainer) -> None:
    """Wire domain event handlers to the event bus.

    Centralises event handler registration so it stays alongside
    the rest of the container configuration.
    """
    from src.modules.collections.application.event_handlers import (
        OnMoviePromotedToSeriesHandler as CollectionsOnMoviePromotedHandler,
    )
    from src.modules.collections.application.event_handlers import (
        OnUserDeletedHandler as CollectionsOnUserDeletedHandler,
    )
    from src.modules.identity.domain.events import UserDeletedEvent
    from src.modules.media.application.event_handlers import OnMediaCreatedHandler
    from src.modules.media.domain.events import (
        MediaCreatedEvent,
        MoviePromotedToSeriesEvent,
    )
    from src.modules.watch_progress.application.event_handlers import (
        OnMoviePromotedToSeriesHandler as ProgressOnMoviePromotedHandler,
    )
    from src.modules.watch_progress.application.event_handlers import (
        OnUserDeletedHandler as ProgressOnUserDeletedHandler,
    )

    event_bus = container.infrastructure.event_bus()

    media_created_handler = OnMediaCreatedHandler(
        enrich_movie_factory=container.media.enrich_movie_metadata,
        enrich_series_factory=container.media.enrich_series_metadata,
    )
    event_bus.subscribe(MediaCreatedEvent, media_created_handler)

    # Cross-BC fan-out when a movie is promoted into a series.
    # watch_progress drops the stale rows (positions can't survive a
    # re-cut episode boundary); collections rewrites watchlist +
    # custom-list refs so the same content stays on the user's lists.
    event_bus.subscribe(
        MoviePromotedToSeriesEvent,
        ProgressOnMoviePromotedHandler(
            uow_factory=container.watch_progress.watch_progress_unit_of_work_factory(),
        ),
    )
    event_bus.subscribe(
        MoviePromotedToSeriesEvent,
        CollectionsOnMoviePromotedHandler(
            uow_factory=container.collections.collections_unit_of_work_factory(),
        ),
    )

    # Cross-BC cleanup when an admin removes a user — watch_progress
    # drops the half-watched positions (privacy), collections wipes
    # the user's watchlists + custom lists (no orphan owner). Each
    # handler runs fire-and-forget so a downstream failure doesn't
    # roll back the identity-side soft-delete.
    event_bus.subscribe(
        UserDeletedEvent,
        ProgressOnUserDeletedHandler(
            uow_factory=container.watch_progress.watch_progress_unit_of_work_factory(),
        ),
    )
    event_bus.subscribe(
        UserDeletedEvent,
        CollectionsOnUserDeletedHandler(
            uow_factory=container.collections.collections_unit_of_work_factory(),
        ),
    )


def _bootstrap_modules() -> None:
    """Run per-module bootstrap hooks (ADR-012).

    Each Bounded Context with cross-cutting wiring exposes a
    ``bootstrap.setup()`` invoked from here. Today this only covers the
    error-code → HTTP-status registration; BCs without such concerns
    are simply omitted from the list.
    """
    from src.modules.identity import bootstrap as identity_bootstrap

    identity_bootstrap.setup()


def create_app() -> FastAPI:
    """Application factory.

    Creates and configures the FastAPI application.

    Returns:
        Configured FastAPI application.
    """
    # Initialize logging first
    setup_logging()

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Personal streaming platform for local media",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Request correlation + timing — must run before routes so the
    # request_id is bound while handlers execute.
    app.add_middleware(RequestContextMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Bootstrap module-level cross-cutting wiring (ADR-012). Must run
    # before the exception handlers are registered so the registry is
    # populated by the time any handler resolves a status.
    _bootstrap_modules()

    # Translate typed exceptions into the standard v3 error envelope
    register_exception_handlers(app)

    # Register routes
    register_health_routes(app)
    app.include_router(admin_relink_router)
    app.include_router(admin_system_router)
    app.include_router(catalog_router)
    app.include_router(collection_router)
    app.include_router(search_router)
    app.include_router(enrichment_router)
    app.include_router(featured_router)
    app.include_router(movie_router)
    app.include_router(people_router)
    app.include_router(scan_router)
    app.include_router(series_router)
    app.include_router(stream_router)
    app.include_router(progress_router)
    app.include_router(watchlist_router)
    app.include_router(custom_list_router)
    app.include_router(catalog_request_router)
    app.include_router(admin_catalog_request_router)
    app.include_router(library_router)
    app.include_router(preferences_router)

    # Identity — FastAPI Users built-in cookie auth (login/logout) plus
    # the custom users / profiles surface that returns prefixed external
    # IDs and routes through the IdentityContainer use cases.
    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/api/v1/auth/cookie",
        tags=["Auth"],
    )
    app.include_router(users_router)
    app.include_router(profile_router)
    app.include_router(admin_user_router)

    return app


def register_health_routes(app: FastAPI) -> None:
    """Register health check endpoints."""

    @app.get("/health", tags=["Health"])  # type: ignore[misc]
    async def health_check() -> dict[str, Any]:
        """Basic health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "0.1.0",
        }

    @app.get("/health/ready", tags=["Health"])  # type: ignore[misc]
    async def readiness_check() -> dict[str, Any]:
        """Readiness check - verifies all dependencies are available."""
        checks = {
            "database": "healthy",  # TODO: Actually check database
            "filesystem": "healthy",  # TODO: Check media directories
        }

        all_healthy = all(status == "healthy" for status in checks.values())

        return {
            "status": "ready" if all_healthy else "not_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        }

    @app.get("/", tags=["Root"])  # type: ignore[misc]
    async def root() -> dict[str, str]:
        """Root endpoint with API information."""
        return {
            "name": "HomeFlix API",
            "version": "0.1.0",
            "docs": "/docs",
        }


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
    )
