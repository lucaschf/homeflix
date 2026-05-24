"""Media bounded context dependency container.

Provides repositories and use cases for the Media module.
"""

from dependency_injector import containers, providers

from src.modules.media.application.event_handlers import OnMediaCreatedHandler
from src.modules.media.application.services.scan_run_service import ScanRunService
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.clear_episode_intro import ClearEpisodeIntroUseCase
from src.modules.media.application.use_cases.clear_hls_cache import ClearHlsCacheUseCase
from src.modules.media.application.use_cases.clear_hls_cache_global import (
    ClearHlsCacheGlobalUseCase,
)
from src.modules.media.application.use_cases.delete_movie import DeleteMovieUseCase
from src.modules.media.application.use_cases.delete_series import DeleteSeriesUseCase
from src.modules.media.application.use_cases.detect_movie_conflicts import (
    DetectMovieConflictsUseCase,
)
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.application.use_cases.generate_hls_playlist import (
    GenerateHlsPlaylistUseCase,
)
from src.modules.media.application.use_cases.get_collection_by_tmdb_id import (
    GetCollectionByTmdbIdUseCase,
)
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase
from src.modules.media.application.use_cases.get_file_tracks import GetFileTracksUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_hls_cache_stats import (
    GetHlsCacheStatsUseCase,
)
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_movie_tmdb_suggestions import (
    GetMovieTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.get_overview_stats import (
    GetOverviewStatsUseCase,
)
from src.modules.media.application.use_cases.get_person_bio import GetPersonBioUseCase
from src.modules.media.application.use_cases.get_related_movies import GetRelatedMoviesUseCase
from src.modules.media.application.use_cases.get_related_series import GetRelatedSeriesUseCase
from src.modules.media.application.use_cases.get_scan_run import GetScanRunUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_movies_by_actor import ListMoviesByActorUseCase
from src.modules.media.application.use_cases.list_movies_needing_review import (
    ListMoviesNeedingReviewUseCase,
)
from src.modules.media.application.use_cases.list_recently_added_catalog import (
    ListRecentlyAddedCatalogUseCase,
)
from src.modules.media.application.use_cases.list_recently_added_movies import (
    ListRecentlyAddedMoviesUseCase,
)
from src.modules.media.application.use_cases.list_recently_added_series import (
    ListRecentlyAddedSeriesUseCase,
)
from src.modules.media.application.use_cases.list_scan_runs import ListScanRunsUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.promote_movie_to_series import (
    PromoteMovieToSeriesUseCase,
)
from src.modules.media.application.use_cases.relink_movie import RelinkMovieUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.resolve_media_conflict import (
    ResolveMediaConflictUseCase,
)
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.application.use_cases.serve_hls_file import ServeHlsFileUseCase
from src.modules.media.application.use_cases.set_episode_intro import SetEpisodeIntroUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.application.use_cases.stream_file_range import StreamFileRangeUseCase
from src.modules.media.application.use_cases.sweep_interrupted_scan_runs import (
    SweepInterruptedScanRunsUseCase,
)
from src.modules.media.application.use_cases.trigger_bulk_enrich import (
    TriggerBulkEnrichUseCase,
)
from src.modules.media.application.use_cases.trigger_scan import TriggerScanUseCase
from src.modules.media.infrastructure.audio import (
    AudioExtractor,
    ChromaprintIntroDetector,
    ChromaprintService,
)
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

    # Wired at the composition root — the adapter lives in the
    # Catalog Requests BC, so this BC only ever sees
    # ``CatalogRequestLookupPort``.
    catalog_request_lookup = providers.Dependency()

    # Wired at the composition root — the adapter reads
    # ``Profile.allowed_library_ids`` via the Identity UoW so this
    # BC only ever sees ``ProfileLibraryAccessPort``.
    profile_library_access = providers.Dependency()

    # Wired at the composition root — the trigger-scan use case
    # needs to look up the requested library before opening the
    # ``scan_runs`` row. Keeps the cross-BC dependency explicit.
    library_uow_factory = providers.Dependency()

    # Wired at the composition root — the OverviewStats aggregator
    # reads the users count from identity. Same pattern as
    # ``library_uow_factory`` above: a read-only cross-BC count
    # for admin dashboard aggregation, not domain coupling.
    identity_uow_factory = providers.Dependency()

    # Must be wired from parent container (Settings.hls_cache_directory).
    # Only the filesystem path remains in ``.env``; ``ffmpeg_threads``
    # and ``hls_cache_max_size_mb`` moved to ``StreamingConfig`` in
    # ADR-013 phase 3 and are read from ``RuntimeSettings``.
    hls_cache_directory = providers.Dependency(default="./hls_cache")

    # RuntimeSettings facade — needed by HlsService, AudioExtractor,
    # ThumbnailGenerationService for streaming config + by
    # IntroDetectionJob (wired from the composition root) for intro
    # tuning. ADR-013.
    runtime_settings = providers.Dependency()

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
        profile_library_access=profile_library_access,
    )

    get_movie_by_id = providers.Factory(
        GetMovieByIdUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_movies = providers.Factory(
        ListMoviesUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_recently_added_movies = providers.Factory(
        ListRecentlyAddedMoviesUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    delete_movie = providers.Factory(
        DeleteMovieUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    delete_series = providers.Factory(
        DeleteSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    get_series_by_id = providers.Factory(
        GetSeriesByIdUseCase,
        uow_factory=media_unit_of_work_factory,
        progress_lookup=progress_lookup,
        profile_library_access=profile_library_access,
    )

    list_series = providers.Factory(
        ListSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_recently_added_series = providers.Factory(
        ListRecentlyAddedSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    # =========================================================================
    # Use Cases — Catalog (cross-cutting movies + series)
    # =========================================================================

    list_genres = providers.Factory(
        ListGenresUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_by_genre = providers.Factory(
        ListByGenreUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_movies_by_actor = providers.Factory(
        ListMoviesByActorUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    list_recently_added_catalog = providers.Factory(
        ListRecentlyAddedCatalogUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
    )

    search_catalog = providers.Factory(
        SearchCatalogUseCase,
        uow_factory=media_unit_of_work_factory,
        profile_library_access=profile_library_access,
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
    # Use Cases — Skip Intro
    # =========================================================================

    set_episode_intro = providers.Factory(
        SetEpisodeIntroUseCase,
        uow_factory=media_unit_of_work_factory,
        event_bus=event_bus,
    )

    clear_episode_intro = providers.Factory(
        ClearEpisodeIntroUseCase,
        uow_factory=media_unit_of_work_factory,
        event_bus=event_bus,
    )

    # =========================================================================
    # Infrastructure — File System
    # =========================================================================

    file_scanner = providers.Factory(LocalFileSystemScanner)

    variant_detector = providers.Factory(VariantDetector)

    media_probe_service = providers.Singleton(MediaProbeService)

    hls_service = providers.Singleton(
        HlsService,
        runtime_settings=runtime_settings,
        cache_dir=hls_cache_directory,
        probe_service=media_probe_service,
        enable_eviction=True,
    )

    # Singleton because ``ThumbnailGenerationService`` is stateless apart
    # from the runtime config it reads per call; sharing one instance
    # across the eager fire-and-forget path (``stream_routes``) and the
    # periodic ``ThumbnailBackfillJob`` keeps configuration in one place.
    thumbnail_generation_service = providers.Singleton(
        ThumbnailGenerationService,
        runtime_settings=runtime_settings,
    )

    # Audio analysis primitives — shared by the periodic intro detection
    # job. Singletons because each wrapper is stateless apart from the
    # runtime config it reads per call, and the job runs them serially
    # per tick.
    audio_extractor = providers.Singleton(
        AudioExtractor,
        runtime_settings=runtime_settings,
    )

    chromaprint_service = providers.Singleton(ChromaprintService)

    intro_detector = providers.Singleton(ChromaprintIntroDetector)

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

    clear_hls_cache_global = providers.Factory(
        ClearHlsCacheGlobalUseCase,
        hls=hls_service,
    )

    get_hls_cache_stats = providers.Factory(
        GetHlsCacheStatsUseCase,
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
        event_bus=event_bus,
    )

    get_related_movies = providers.Factory(
        GetRelatedMoviesUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
        profile_library_access=profile_library_access,
    )

    get_collection_by_tmdb_id = providers.Factory(
        GetCollectionByTmdbIdUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
        catalog_request_lookup=catalog_request_lookup,
        profile_library_access=profile_library_access,
    )

    get_person_bio = providers.Factory(
        GetPersonBioUseCase,
        metadata_provider=tmdb_client,
    )

    enrich_series_metadata = providers.Factory(
        EnrichSeriesMetadataUseCase,
        uow_factory=media_unit_of_work_factory,
        primary_provider=tmdb_client,
        event_bus=event_bus,
    )

    get_related_series = providers.Factory(
        GetRelatedSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
        profile_library_access=profile_library_access,
    )

    bulk_enrich_metadata = providers.Factory(
        BulkEnrichMetadataUseCase,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
        uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Scan + Enrich admin runs
    # =========================================================================

    scan_run_service = providers.Singleton(
        ScanRunService,
        scan_use_case=scan_media_directories,
        bulk_enrich_use_case=bulk_enrich_metadata,
        media_uow_factory=media_unit_of_work_factory,
    )

    trigger_scan = providers.Factory(
        TriggerScanUseCase,
        scan_run_service=scan_run_service,
        library_uow_factory=library_uow_factory,
    )

    trigger_bulk_enrich = providers.Factory(
        TriggerBulkEnrichUseCase,
        scan_run_service=scan_run_service,
    )

    list_scan_runs = providers.Factory(
        ListScanRunsUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    get_scan_run = providers.Factory(
        GetScanRunUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    sweep_interrupted_scan_runs = providers.Factory(
        SweepInterruptedScanRunsUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Use Cases — Admin Overview aggregator
    # =========================================================================

    # Declared here so it can reach ``list_movies_needing_review``
    # below — order in the container is purely for readability.
    # The actual provider is appended after the review use case
    # so its reference resolves cleanly.

    # =========================================================================
    # Use Cases — Admin Relink
    # =========================================================================

    list_movies_needing_review = providers.Factory(
        ListMoviesNeedingReviewUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    get_overview_stats = providers.Factory(
        GetOverviewStatsUseCase,
        media_uow_factory=media_unit_of_work_factory,
        identity_uow_factory=identity_uow_factory,
        list_movies_needing_review=list_movies_needing_review,
        hls_playlist=hls_service,
    )

    get_movie_tmdb_suggestions = providers.Factory(
        GetMovieTmdbSuggestionsUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
    )

    relink_movie = providers.Factory(
        RelinkMovieUseCase,
        uow_factory=media_unit_of_work_factory,
        enrich_use_case=enrich_movie_metadata,
    )

    promote_movie_to_series = providers.Factory(
        PromoteMovieToSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
        enrich_series_use_case=enrich_series_metadata,
        event_bus=event_bus,
    )

    # =========================================================================
    # Use Cases — Conflict Detection (ADR-015 Phase 1)
    # =========================================================================

    detect_movie_conflicts = providers.Factory(
        DetectMovieConflictsUseCase,
        uow_factory=media_unit_of_work_factory,
        event_bus=event_bus,
    )

    list_conflicts = providers.Factory(
        ListConflictsUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    resolve_media_conflict = providers.Factory(
        ResolveMediaConflictUseCase,
        uow_factory=media_unit_of_work_factory,
        event_bus=event_bus,
    )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    on_media_created_handler = providers.Singleton(
        OnMediaCreatedHandler,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
    )
