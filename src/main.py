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
from src.modules.media.presentation.routes import movie_router, series_router


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
            "src.modules.media.presentation.routes.movie_routes",
            "src.modules.media.presentation.routes.series_routes",
        ],
    )
    app.state.container = container

    logger.info("Application ready")

    yield

    # Shutdown
    logger.info("Application shutting down")

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
    app.include_router(movie_router)
    app.include_router(series_router)

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
