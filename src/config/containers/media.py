"""Media bounded context dependency container.

Provides repositories and use cases for the Media module.
"""

from dependency_injector import containers, providers

from src.modules.media.application.event_handlers import OnMediaCreatedHandler
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.delete_movie import DeleteMovieUseCase
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.metadata.tmdb_client import TmdbClient
from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.streaming import HlsService, MediaProbeService
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)


class MediaContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Media bounded context dependencies.

    Provides:
    - Repository implementations (SQLAlchemy)
    - Use cases for movie, series, and file variant operations

    The ``session`` dependency must be wired from the parent container
    once the database provider is added to InfrastructureContainer.

    Example:
        >>> container = MediaContainer(session=session_provider)
        >>> use_case = container.get_movie_by_id()
    """

    # Must be wired from InfrastructureContainer
    session = providers.Dependency()
    event_bus = providers.Dependency()

    # Must be wired from parent container (Settings.hls_cache_directory)
    hls_cache_directory = providers.Dependency(default="./hls_cache")

    # =========================================================================
    # Repositories
    # =========================================================================

    movie_repository = providers.Factory(
        SQLAlchemyMovieRepository,
        session=session,
    )

    series_repository = providers.Factory(
        SQLAlchemySeriesRepository,
        session=session,
    )

    progress_repository = providers.Factory(
        SQLAlchemyWatchProgressRepository,
        session=session,
    )

    # =========================================================================
    # Use Cases — Query
    # =========================================================================

    get_featured_media = providers.Factory(
        GetFeaturedMediaUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    get_movie_by_id = providers.Factory(
        GetMovieByIdUseCase,
        movie_repository=movie_repository,
    )

    list_movies = providers.Factory(
        ListMoviesUseCase,
        movie_repository=movie_repository,
    )

    delete_movie = providers.Factory(
        DeleteMovieUseCase,
        movie_repository=movie_repository,
    )

    get_series_by_id = providers.Factory(
        GetSeriesByIdUseCase,
        series_repository=series_repository,
        progress_repository=progress_repository,
    )

    list_series = providers.Factory(
        ListSeriesUseCase,
        series_repository=series_repository,
    )

    # =========================================================================
    # Use Cases — File Variants
    # =========================================================================

    get_file_variants = providers.Factory(
        GetFileVariantsUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    add_file_variant = providers.Factory(
        AddFileVariantUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    remove_file_variant = providers.Factory(
        RemoveFileVariantUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    set_primary_file = providers.Factory(
        SetPrimaryFileUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    # =========================================================================
    # Infrastructure — File System
    # =========================================================================

    file_scanner = providers.Factory(LocalFileSystemScanner)

    variant_detector = providers.Factory(VariantDetector)

    media_probe_service = providers.Singleton(MediaProbeService)

    hls_service = providers.Singleton(
        HlsService,
        cache_dir=hls_cache_directory,
        probe_service=media_probe_service,
    )

    # =========================================================================
    # Use Cases — Scan
    # =========================================================================

    scan_media_directories = providers.Factory(
        ScanMediaDirectoriesUseCase,
        file_scanner=file_scanner,
        variant_detector=variant_detector,
        movie_repository=movie_repository,
        series_repository=series_repository,
        event_bus=event_bus,
    )

    # =========================================================================
    # Infrastructure — Metadata Providers
    # =========================================================================

    # Must be wired from parent container (Settings.tmdb_api_key)
    tmdb_api_key = providers.Dependency(default="")

    tmdb_client = providers.Singleton(TmdbClient, api_key=tmdb_api_key)

    # =========================================================================
    # Use Cases — Enrichment
    # =========================================================================

    enrich_movie_metadata = providers.Factory(
        EnrichMovieMetadataUseCase,
        movie_repository=movie_repository,
        primary_provider=tmdb_client,
    )

    enrich_series_metadata = providers.Factory(
        EnrichSeriesMetadataUseCase,
        series_repository=series_repository,
        primary_provider=tmdb_client,
    )

    bulk_enrich_metadata = providers.Factory(
        BulkEnrichMetadataUseCase,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    on_media_created_handler = providers.Singleton(
        OnMediaCreatedHandler,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
    )
