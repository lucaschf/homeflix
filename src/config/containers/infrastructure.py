"""Infrastructure layer dependency container.

Provides database connections, external API clients, and other
infrastructure components.
"""

from dependency_injector import containers, providers

from src.config.settings import Settings


class InfrastructureContainer(containers.DeclarativeContainer):
    """Container for infrastructure dependencies.

    Includes:
    - Database connections
    - External API clients (TMDB, OMDb)
    - File system services
    """

    # Settings is provided by parent container
    config = providers.Dependency(instance_of=Settings)

    # =========================================================================
    # Database
    # =========================================================================

    # TODO: Uncomment when Database class is implemented
    # database = providers.Singleton(
    #     Database,
    #     url=config.provided.database_url,
    # )

    # =========================================================================
    # External API Clients
    # =========================================================================

    # TODO: Uncomment when TMDBClient is implemented
    # tmdb_client = providers.Singleton(
    #     TMDBClient,
    #     api_key=config.provided.tmdb_api_key,
    #     base_url=config.provided.tmdb_base_url,
    # )

    # TODO: Uncomment when OMDbClient is implemented
    # omdb_client = providers.Singleton(
    #     OMDbClient,
    #     api_key=config.provided.omdb_api_key,
    # )

    # =========================================================================
    # File System
    # =========================================================================

    # TODO: Uncomment when FileScanner is implemented
    # file_scanner = providers.Factory(
    #     FileScanner,
    #     media_directories=config.provided.media_directories,
    # )
    #
    # thumbnail_generator = providers.Factory(
    #     ThumbnailGenerator,
    #     output_directory=config.provided.thumbnails_path,
    # )
