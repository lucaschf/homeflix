"""Media bounded context dependency container.

Provides repositories and use cases for the Media module.
"""

from typing import Any

from dependency_injector import containers, providers

from src.modules.media.application.event_handlers import OnMediaCreatedHandler
from src.modules.media.application.services.job_run_service import JobRunService
from src.modules.media.application.services.scan_run_service import ScanRunService
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.bulk_mark_distinct_conflicts import (
    BulkMarkDistinctConflictsUseCase,
)
from src.modules.media.application.use_cases.clear_credits_marker import (
    ClearCreditsMarkerUseCase,
)
from src.modules.media.application.use_cases.clear_episode_intro import ClearEpisodeIntroUseCase
from src.modules.media.application.use_cases.define_episode_segments import (
    DefineEpisodeSegmentsUseCase,
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
from src.modules.media.application.use_cases.flag_movie_enrichment_review import (
    FlagMovieEnrichmentReviewUseCase,
)
from src.modules.media.application.use_cases.flag_series_enrichment_review import (
    FlagSeriesEnrichmentReviewUseCase,
)
from src.modules.media.application.use_cases.get_collection_by_tmdb_id import (
    GetCollectionByTmdbIdUseCase,
)
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_intro_detection_run import (
    GetIntroDetectionRunUseCase,
)
from src.modules.media.application.use_cases.get_library_usage import (
    GetLibraryUsageUseCase,
)
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_movie_tmdb_suggestions import (
    GetMovieTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.get_overview_stats import (
    GetOverviewStatsUseCase,
)
from src.modules.media.application.use_cases.get_related_movies import GetRelatedMoviesUseCase
from src.modules.media.application.use_cases.get_related_series import GetRelatedSeriesUseCase
from src.modules.media.application.use_cases.get_scan_run import GetScanRunUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.get_series_tmdb_suggestions import (
    GetSeriesTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.application.use_cases.list_credits_status import (
    ListCreditsStatusUseCase,
)
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.application.use_cases.list_intro_detection_runs import (
    ListIntroDetectionRunsUseCase,
)
from src.modules.media.application.use_cases.list_job_runs import ListJobRunsUseCase
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
from src.modules.media.application.use_cases.list_series_needing_review import (
    ListSeriesNeedingReviewUseCase,
)
from src.modules.media.application.use_cases.promote_movie_to_series import (
    PromoteMovieToSeriesUseCase,
)
from src.modules.media.application.use_cases.relink_movie import RelinkMovieUseCase
from src.modules.media.application.use_cases.relink_series import RelinkSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.reset_credits_detection import (
    ResetCreditsDetectionUseCase,
)
from src.modules.media.application.use_cases.reset_season_intro_detection import (
    ResetSeasonIntroDetectionUseCase,
)
from src.modules.media.application.use_cases.resolve_media_conflict import (
    ResolveMediaConflictUseCase,
)
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase
from src.modules.media.application.use_cases.search_tmdb_titles import (
    SearchTmdbTitlesUseCase,
)
from src.modules.media.application.use_cases.set_credits_marker import SetCreditsMarkerUseCase
from src.modules.media.application.use_cases.set_episode_intro import SetEpisodeIntroUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.application.use_cases.sweep_interrupted_job_runs import (
    SweepInterruptedJobRunsUseCase,
)
from src.modules.media.application.use_cases.sweep_interrupted_scan_runs import (
    SweepInterruptedScanRunsUseCase,
)
from src.modules.media.application.use_cases.sweep_movie_conflicts import (
    SweepMovieConflictsUseCase,
)
from src.modules.media.application.use_cases.trigger_bulk_enrich import (
    TriggerBulkEnrichUseCase,
)
from src.modules.media.application.use_cases.trigger_scan import TriggerScanUseCase
from src.modules.media.infrastructure.acl.identity_user_count_adapter import (
    IdentityUserCountAdapter,
)
from src.modules.media.infrastructure.acl.library_lookup_adapter import (
    LibraryLookupAdapter,
)
from src.modules.media.infrastructure.audio import (
    AudioExtractor,
    ChromaprintIntroDetector,
    ChromaprintService,
)
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.modules.media.infrastructure.video import (
    CreditsDetector,
    FrameHasher,
    FrameHashIntroDetector,
)


class MediaContainer(containers.DeclarativeContainer):
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
    session_factory = providers.Dependency[Any]()
    event_bus = providers.Dependency[Any]()

    # Wired at the composition root — the adapter depends on the
    # Watch Progress UoW factory so the Media BC only knows the port.
    progress_lookup = providers.Dependency[Any]()

    # Wired at the composition root — the adapter lives in the
    # Catalog Requests BC, so this BC only ever sees
    # ``CatalogRequestLookupPort``.
    catalog_request_lookup = providers.Dependency[Any]()

    # Wired at the composition root — the adapter reads
    # ``Profile.allowed_library_ids`` via the Identity UoW so this
    # BC only ever sees ``ProfileLibraryAccessPort``.
    profile_library_access = providers.Dependency[Any]()

    # Wired at the composition root — the trigger-scan use case
    # needs to look up the requested library before opening the
    # ``scan_runs`` row. Keeps the cross-BC dependency explicit.
    library_uow_factory = providers.Dependency[Any]()

    # Wired at the composition root — ADR-015 Phase 3 detector uses
    # this port to distinguish a real orphan (file moved/deleted by
    # the operator) from transient I/O failure (drive unmounted).
    library_health = providers.Dependency[Any]()

    # Wired at the composition root — the OverviewStats aggregator
    # reads the users count from identity. Same pattern as
    # ``library_uow_factory`` above: a read-only cross-BC count
    # for admin dashboard aggregation, not domain coupling.
    identity_uow_factory = providers.Dependency[Any]()

    # Wired at the composition root — ADR-026: the /tracks use case reads
    # the viewing profile's preferred audio language from the Preferences BC
    # to pick the default audio track at read time.
    preferences_uow_factory = providers.Dependency[Any]()

    # Wired at the composition root from the Streaming BC (ADR-032): the
    # ffprobe-backed probe service (shared, one instance) used by the scan
    # and segment use cases, the media-side scrub-preview locator ACL
    # adapter used by the scan, and the HLS cache-stats read port used by
    # the admin overview aggregator. Overridden after StreamingContainer is
    # composed so the mutual media<->streaming wiring stays acyclic.
    media_probe_service = providers.Dependency[Any]()
    scrub_preview_locator = providers.Dependency[Any]()
    hls_cache_stats = providers.Dependency[Any]()

    # RuntimeSettings facade — needed by HlsService, AudioExtractor,
    # ThumbnailGenerationService for streaming config + by
    # IntroDetectionJob (wired from the composition root) for intro
    # tuning. ADR-013.
    runtime_settings = providers.Dependency[Any]()

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

    reset_season_intro_detection = providers.Factory(
        ResetSeasonIntroDetectionUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    set_credits_marker = providers.Factory(
        SetCreditsMarkerUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    clear_credits_marker = providers.Factory(
        ClearCreditsMarkerUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    reset_credits_detection = providers.Factory(
        ResetCreditsDetectionUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    list_credits_status = providers.Factory(
        ListCreditsStatusUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    # =========================================================================
    # Infrastructure — File System
    # =========================================================================

    file_scanner = providers.Factory(LocalFileSystemScanner)

    variant_detector = providers.Factory(VariantDetector)

    # Cross-BC read ports (ADR-009 ACL): the scan flow resolves a
    # library's paths and the overview reads the users count without
    # importing the Library / Identity Unit of Work above the adapter.
    library_lookup = providers.Singleton(
        LibraryLookupAdapter,
        library_uow_factory=library_uow_factory,
    )
    identity_user_count = providers.Singleton(
        IdentityUserCountAdapter,
        identity_uow_factory=identity_uow_factory,
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

    # Each detector owns its full pipeline (extraction + hashing +
    # cross-correlation) behind IntroDetectorPort; the job picks one per
    # tick by IntroDetectionConfig.algorithm and only ever sees the
    # abstraction.
    chromaprint_intro_detector = providers.Singleton(
        ChromaprintIntroDetector,
        audio_extractor=audio_extractor,
        chromaprint_service=chromaprint_service,
    )

    frame_hasher = providers.Singleton(
        FrameHasher,
        runtime_settings=runtime_settings,
    )

    frame_hash_intro_detector = providers.Singleton(
        FrameHashIntroDetector,
        frame_hasher=frame_hasher,
    )

    # Per-file end-credits detector (combined edge + low-motion signals)
    # behind CreditsDetectorPort; consumed by the CreditsDetectionJob
    # wired from the composition root.
    credits_detector = providers.Singleton(
        CreditsDetector,
        runtime_settings=runtime_settings,
    )

    # =========================================================================
    # Use Cases — Library usage (admin overview)
    # =========================================================================

    get_library_usage = providers.Factory(
        GetLibraryUsageUseCase,
        uow_factory=media_unit_of_work_factory,
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
        scrub_preview_locator=scrub_preview_locator,
    )

    define_episode_segments = providers.Factory(
        DefineEpisodeSegmentsUseCase,
        uow_factory=media_unit_of_work_factory,
        probe_service=media_probe_service,
    )

    # =========================================================================
    # Infrastructure — Metadata Providers
    # =========================================================================

    # Wired at the composition root from the Metadata BC (ADR-032): the
    # TMDB gateway (``MetadataProvider``) the enrichment / relink /
    # suggestion use cases orchestrate. Media consumes the provider port
    # published by the Metadata module — the Core-depends-on-Supporting
    # provider-contract dependency — same cross-container wiring as
    # ``library`` receiving ``media.media_unit_of_work_factory``.
    tmdb_client = providers.Dependency[Any]()

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
        library_lookup=library_lookup,
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

    list_intro_detection_runs = providers.Factory(
        ListIntroDetectionRunsUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    get_intro_detection_run = providers.Factory(
        GetIntroDetectionRunUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    sweep_interrupted_scan_runs = providers.Factory(
        SweepInterruptedScanRunsUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    # Background-jobs dashboard: a recorder the scheduler wraps every job
    # with, plus read use cases for the history list.
    job_run_service = providers.Singleton(
        JobRunService,
        media_uow_factory=media_unit_of_work_factory,
    )

    list_job_runs = providers.Factory(
        ListJobRunsUseCase,
        media_uow_factory=media_unit_of_work_factory,
    )

    sweep_interrupted_job_runs = providers.Factory(
        SweepInterruptedJobRunsUseCase,
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
        user_count=identity_user_count,
        list_movies_needing_review=list_movies_needing_review,
        hls_cache_stats=hls_cache_stats,
    )

    get_movie_tmdb_suggestions = providers.Factory(
        GetMovieTmdbSuggestionsUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
    )

    search_tmdb_titles = providers.Factory(
        SearchTmdbTitlesUseCase,
        metadata_provider=tmdb_client,
        uow_factory=media_unit_of_work_factory,
    )

    relink_movie = providers.Factory(
        RelinkMovieUseCase,
        uow_factory=media_unit_of_work_factory,
        enrich_use_case=enrich_movie_metadata,
    )

    flag_movie_enrichment_review = providers.Factory(
        FlagMovieEnrichmentReviewUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    list_series_needing_review = providers.Factory(
        ListSeriesNeedingReviewUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    flag_series_enrichment_review = providers.Factory(
        FlagSeriesEnrichmentReviewUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    get_series_tmdb_suggestions = providers.Factory(
        GetSeriesTmdbSuggestionsUseCase,
        uow_factory=media_unit_of_work_factory,
        metadata_provider=tmdb_client,
    )

    relink_series = providers.Factory(
        RelinkSeriesUseCase,
        uow_factory=media_unit_of_work_factory,
        enrich_use_case=enrich_series_metadata,
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
        library_health=library_health,
        event_bus=event_bus,
        runtime_settings=runtime_settings,
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

    bulk_mark_distinct_conflicts = providers.Factory(
        BulkMarkDistinctConflictsUseCase,
        uow_factory=media_unit_of_work_factory,
    )

    sweep_movie_conflicts = providers.Factory(
        SweepMovieConflictsUseCase,
        uow_factory=media_unit_of_work_factory,
        detect_use_case=detect_movie_conflicts,
    )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    on_media_created_handler = providers.Singleton(
        OnMediaCreatedHandler,
        enrich_movie=enrich_movie_metadata,
        enrich_series=enrich_series_metadata,
    )
