"""Main application container.

Composes all sub-containers into a single container that serves
as the composition root for the application.

See ADR-004 for the rationale behind this design.
"""

from dependency_injector import containers, providers

from src.config.containers.infrastructure import InfrastructureContainer
from src.config.settings import Settings


class ApplicationContainer(containers.DeclarativeContainer):
    """Main application dependency injection container.

    This container composes all sub-containers and serves as the
    single entry point for dependency resolution.

    Structure:
        ApplicationContainer
        ├── config (Settings)
        └── infrastructure (InfrastructureContainer)
            ├── database
            └── ...

    Bounded context containers (repositories, use_cases) are added
    as each context is implemented.

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


# Convenience alias
Container = ApplicationContainer
