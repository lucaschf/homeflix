"""Media bounded context dependency container.

Provides repositories and use cases for the Media module.
"""

from dependency_injector import containers, providers

from src.modules.media.application.event_handlers import OnMediaCreatedHandler
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.clear_hls_cache import ClearHlsCacheUseCase
from src.modules.media.application.use_cases.delete_movie import DeleteMovieUseCase
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.application.use_cases.generate_hls_playlist import (
    GenerateHlsPlaylistUseCase,
)
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase
from src.modules.media.application.use_cases.get_file_tracks import GetFileTracksUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.application.use_cases.serve_hls_file import ServeHlsFileUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.application.use_cases.stream_file_range import StreamFileRangeUseCase
from src.modules.media.infrastructure.acl import ProgressLookupAdapter
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.metadata.tmdb_client import TmdbClient
from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
    SQLAlchemyMovieRepository,
)
from src.modules.media.infrastructure.persistence.repositories.series_repository import (
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.modules.media.infrastructure.streaming import HlsService, MediaProbeService
from src.modules.media.infrastructure.streaming.file_streamer import LocalFileStreamer
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)


class MediaContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Media bounded context dependencies.

    Provides:
    - Repository implementations (SQLAlchemy)
    - Use cases for movie, series, and file variant operations
    - ACL adapter for the Watch Progress BC read port

    The ``session`` dependency must be wired from the parent container
    once the database provider is added to InfrastructureContainer.

    Example:
        >>> container = MediaContainer(session=session_provider)
        >>> use_case = container.get_movie_by_id()
    """

    # Must be wired from InfrastructureContainer
    session = providers.Dependency()
    session_factory = providers.Dependency()
    event_bus = providers.Dependency()

    # Must be wired from parent container (Settings.hls_cache_directory / hls_cache_max_size_mb)
    hls_cache_directory = providers.Dependency(default="./hls_cache")
    hls_cache_max_size_mb = providers.Dependency(default=5120)

    # =========================================================================
    # Repositories (read-only use cases) and Unit of Work (writes)
    # =========================================================================

    movie_repository = providers.Factory(
        SQLAlchemyMovieRepository,
        session=session,
    )

    series_repository = providers.Factory(
        SQLAlchemySeriesRepository,
        session=session,
    )

    media_unit_of_work_factory = providers.Singleton(
        SqlAlchemyMediaUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read ports)
    # =========================================================================
    # Wraps the Watch Progress repository so media use cases see only
    # the ``ProgressLookupPort`` and never import progress domain types.
    # Each request builds a fresh adapter bound to the request session.

    _progress_repository = providers.Factory(
        SQLAlchemyWatchProgressRepository,
        session=session,
    )

    progress_lookup = providers.Factory(
        ProgressLookupAdapter,
        progress_repository=_progress_repository,
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
        uow_factory=media_unit_of_work_factory,
    )

    get_series_by_id = providers.Factory(
        GetSeriesByIdUseCase,
        series_repository=series_repository,
        progress_lookup=progress_lookup,
    )

    list_series = providers.Factory(
        ListSeriesUseCase,
        series_repository=series_repository,
    )

    # =========================================================================
    # Use Cases — Catalog (cross-cutting movies + series)
    # =========================================================================

    list_genres = providers.Factory(
        ListGenresUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    list_by_genre = providers.Factory(
        ListByGenreUseCase,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    search_catalog = providers.Factory(
        SearchCatalogUseCase,
        movie_repository=movie_repository,
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
        uow_factory=media_unit_of_work_factory,
    )

    remove_file_variant = providers.Factory(
        RemoveFileVariantUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    set_primary_file = providers.Factory(
        SetPrimaryFileUseCase,
        uow_factory=media_unit_of_work_factory,
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
        enable_eviction=True,
        max_cache_size_mb=hls_cache_max_size_mb,
    )

    file_streamer = providers.Factory(LocalFileStreamer)

    # =========================================================================
    # Use Cases — Streaming
    # =========================================================================

    generate_hls_playlist = providers.Factory(
        GenerateHlsPlaylistUseCase,
        hls=hls_service,
    )

    serve_hls_file = providers.Factory(
        ServeHlsFileUseCase,
        hls=hls_service,
    )

    get_file_tracks = providers.Factory(
        GetFileTracksUseCase,
        hls=hls_service,
    )

    clear_hls_cache = providers.Factory(
        ClearHlsCacheUseCase,
        hls=hls_service,
    )

    stream_file_range = providers.Factory(
        StreamFileRangeUseCase,
        file_streamer=file_streamer,
    )

    # =========================================================================
    # Use Cases — Scan
    # =========================================================================

    scan_media_directories = providers.Factory(
        ScanMediaDirectoriesUseCase,
        file_scanner=file_scanner,
        variant_detector=variant_detector,
        uow_factory=media_unit_of_work_factory,
        probe_service=media_probe_service,
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
        uow_factory=media_unit_of_work_factory,
        primary_provider=tmdb_client,
    )

    enrich_series_metadata = providers.Factory(
        EnrichSeriesMetadataUseCase,
        uow_factory=media_unit_of_work_factory,
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
