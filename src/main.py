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

from src.config.containers import ApplicationContainer
from src.config.logging import get_logger, setup_logging
from src.config.settings import get_settings
from src.modules.collections.presentation.routes import custom_list_router, watchlist_router
from src.modules.media.presentation.routes import (
    enrichment_router,
    featured_router,
    movie_router,
    scan_router,
    series_router,
    stream_router,
)
from src.modules.watch_progress.presentation.routes import progress_router


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
    container.wire(
        modules=[
            "src.modules.media.presentation.routes.enrichment_routes",
            "src.modules.media.presentation.routes.featured_routes",
            "src.modules.media.presentation.routes.movie_routes",
            "src.modules.media.presentation.routes.scan_routes",
            "src.modules.media.presentation.routes.series_routes",
            "src.modules.media.presentation.routes.stream_routes",
            "src.modules.watch_progress.presentation.routes.progress_routes",
            "src.modules.collections.presentation.routes.watchlist_routes",
            "src.modules.collections.presentation.routes.custom_list_routes",
        ],
    )
    app.state.container = container

    # Initialize database
    await container.infrastructure.init_resources()

    logger.info("Application ready")

    yield

    # Shutdown
    logger.info("Application shutting down")
    await container.infrastructure.shutdown_resources()
    logger.info("Application stopped")


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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_health_routes(app)
    app.include_router(enrichment_router)
    app.include_router(featured_router)
    app.include_router(movie_router)
    app.include_router(scan_router)
    app.include_router(series_router)
    app.include_router(stream_router)
    app.include_router(progress_router)
    app.include_router(watchlist_router)
    app.include_router(custom_list_router)

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
