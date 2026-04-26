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
from src.modules.media.application.use_cases.get_related_movies import GetRelatedMoviesUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_movies_by_actor import ListMoviesByActorUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.application.use_cases.serve_hls_file import ServeHlsFileUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.application.use_cases.stream_file_range import StreamFileRangeUseCase
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.metadata.tmdb_client import TmdbClient
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.modules.media.infrastructure.streaming import HlsService, MediaProbeService
from src.modules.media.infrastructure.streaming.file_streamer import LocalFileStreamer
from src.modules.media.infrastructure.streaming.thumbnail_service import (
    ThumbnailGenerationService,
)


class MediaContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Media bounded context dependencies.

    Provides:
    - Unit of Work factory (covers both reads and writes)
    - Use cases for movie, series, and file variant operations
    - Streaming and metadata infrastructure

    The ``session_factory``, ``event_bus``, and ``progress_lookup``
    dependencies must be wired from the parent container.

    Example:
        >>> container = MediaContainer(session_factory=sf, ...)
        >>> use_case = container.get_movie_by_id()
    """

    # Must be wired from InfrastructureContainer
    session_factory = providers.Dependency()
    event_bus = providers.Dependency()

    # Wired at the composition root — the adapter depends on the
    # Watch Progress UoW factory so the Media BC only knows the port.
    progress_lookup = providers.Dependency()

    # Must be wired from parent container (Settings.hls_cache_directory / hls_cache_max_size_mb)
    hls_cache_directory = providers.Dependency(default="./hls_cache")
    hls_cache_max_size_mb = providers.Dependency(default=5120)

    # Optional global cap on ffmpeg worker threads. ``None`` keeps the
    # auto-default (all cores). Wired from ``Settings.ffmpeg_threads``.
    ffmpeg_threads = providers.Dependency(default=None)

    # =========================================================================
    # Unit of Work
    # =========================================================================

    media_unit_of_work_factory = providers.Singleton(
        SqlAlchemyMediaUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Use Cases — Query
    # =========================================================================

    get_featured_media = providers.Factory(
        GetFeaturedMediaUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    get_movie_by_id = providers.Factory(
        GetMovieByIdUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    list_movies = providers.Factory(
        ListMoviesUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    delete_movie = providers.Factory(
        DeleteMovieUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    get_series_by_id = providers.Factory(
        GetSeriesByIdUseCase,
        uow_factory=media_unit_of_work_factory,
        progress_lookup=progress_lookup,
    )

    list_series = providers.Factory(
        ListSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Use Cases — Catalog (cross-cutting movies + series)
    # =========================================================================

    list_genres = providers.Factory(
        ListGenresUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    list_by_genre = providers.Factory(
        ListByGenreUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    list_movies_by_actor = providers.Factory(
        ListMoviesByActorUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    search_catalog = providers.Factory(
        SearchCatalogUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Use Cases — File Variants
    # =========================================================================

    get_file_variants = providers.Factory(
        GetFileVariantsUseCase,
        uow_factory=media_unit_of_work_factory,
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
        ffmpeg_threads=ffmpeg_threads,
    )

    # Singleton because ``ThumbnailGenerationService`` is stateless apart
    # from the configured thread cap; sharing one instance across the
    # eager fire-and-forget path (``stream_routes``) and the periodic
    # ``ThumbnailBackfillJob`` keeps configuration in one place.
    thumbnail_generation_service = providers.Singleton(
        ThumbnailGenerationService,
        ffmpeg_threads=ffmpeg_threads,
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

    get_related_movies = providers.Factory(
        GetRelatedMoviesUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
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
        uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    on_media_created_handler = providers.Singleton(
        OnMediaCreatedHandler,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
    )
