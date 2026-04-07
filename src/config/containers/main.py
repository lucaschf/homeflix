"""Main application container.

Composes all sub-containers into a single container that serves
as the composition root for the application.

See ADR-004 for the rationale behind this design.
"""

from dependency_injector import containers, providers

from src.config.containers.infrastructure import InfrastructureContainer
from src.config.containers.library import LibraryContainer
from src.config.containers.media import MediaContainer
from src.config.settings import Settings


class ApplicationContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Main application dependency injection container.

    This container composes all sub-containers and serves as the
    single entry point for dependency resolution.

    Structure:
        ApplicationContainer
        ├── config (Settings)
        ├── infrastructure (InfrastructureContainer)
        ├── media (MediaContainer)
        └── library (LibraryContainer)

    Example:
        >>> container = ApplicationContainer()
        >>> container.wire()
        >>> settings = container.config()
    """

    # =========================================================================
    # Configuration
    # =========================================================================

    config = providers.Singleton(Settings)

    # =========================================================================
    # Sub-Containers
    # =========================================================================

    infrastructure = providers.Container(
        InfrastructureContainer,
        config=config,
    )

    # =========================================================================
    # Bounded Context Containers
    # =========================================================================

    media = providers.Container(
        MediaContainer,
        session=infrastructure.session,
        tmdb_api_key=config.provided.tmdb_api_key,
        hls_cache_directory=config.provided.hls_cache_directory,
    )

    library = providers.Container(LibraryContainer)


# Convenience alias
Container = ApplicationContainer
