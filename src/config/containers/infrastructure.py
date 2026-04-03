"""Infrastructure layer dependency container.

Provides database connections, external API clients, and other
infrastructure components.
"""

from dependency_injector import containers, providers

from src.config.settings import Settings


class InfrastructureContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for infrastructure dependencies.

    Includes:
    - Database connections
    - External API clients (TMDB, OMDb)
    - File system services

    Note:
        Database, external API clients, and file system services
        will be added as providers when their implementations are ready.
    """

    # Settings is provided by parent container
    config = providers.Dependency(instance_of=Settings)
