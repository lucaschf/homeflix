"""Main application container.

Composes all sub-containers into a single container that serves
as the composition root for the application.

See ADR-004 for the rationale behind this design.
"""

from dependency_injector import containers, providers

from src.config.containers.catalog_requests import CatalogRequestsContainer
from src.config.containers.collections import CollectionsContainer
from src.config.containers.identity import IdentityContainer
from src.config.containers.infrastructure import InfrastructureContainer
from src.config.containers.library import LibraryContainer
from src.config.containers.media import MediaContainer
from src.config.containers.metadata import MetadataContainer
from src.config.containers.notifications import NotificationsContainer
from src.config.containers.preferences import PreferencesContainer
from src.config.containers.settings import SettingsContainer
from src.config.containers.streaming import StreamingContainer
from src.config.containers.watch_progress import WatchProgressContainer
from src.config.settings import Settings
from src.infrastructure.health import DatabaseProbe, FilesystemProbe
from src.infrastructure.scheduling import (
    ArtworkMirrorJob,
    CreditsDetectionJob,
    IntroDetectionJob,
    LibraryScanScheduler,
    ScanDedupSweepJob,
    SubtitleOcrBackfillJob,
    ThumbnailBackfillJob,
)
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)
from src.modules.media.application.use_cases.list_jobs import ListJobsUseCase
from src.modules.media.application.use_cases.reset_season_intro_detection import (
    ResetSeasonIntroDetectionUseCase,
)
from src.modules.media.application.use_cases.trigger_job import TriggerJobUseCase
from src.modules.media.infrastructure.acl import (
    HlsCacheStatsAdapter,
    LibraryHealthAdapter,
    ProfileLibraryAccessAdapter,
    ProgressLookupAdapter,
    ScrubPreviewLocatorAdapter,
    TmdbLocalizedTitleAdapter,
    WatchHistoryAdapter,
)
from src.modules.media.infrastructure.scheduling.intro_detection_runner import (
    BackgroundIntroDetectionRunner,
)
from src.modules.media.infrastructure.scheduling.scheduler_controller import (
    LibraryScanSchedulerController,
)
from src.modules.media.infrastructure.scheduling.scheduler_inspector import (
    LibraryScanSchedulerInspector,
)
from src.modules.metadata.infrastructure.tmdb_client import TmdbClient
from src.modules.preferences.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyPreferencesUnitOfWorkFactory,
)
from src.modules.settings.domain.value_objects import IntroDetectionAlgorithm
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)


class ApplicationContainer(containers.DeclarativeContainer):
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

    # Cross-BC adapter: Media use cases that resolve watch progress go
    # through this port. Built here rather than inside MediaContainer
    # so the Media BC does not take a circular dependency on the full
    # WatchProgressContainer (which itself consumes
    # ``media.media_unit_of_work_factory``).
    _watch_progress_uow_factory_for_progress_lookup = providers.Singleton(
        SqlAlchemyWatchProgressUnitOfWorkFactory,
        session_factory=infrastructure.session_factory,
    )

    _progress_lookup_adapter = providers.Factory(
        ProgressLookupAdapter,
        watch_progress_uow_factory=_watch_progress_uow_factory_for_progress_lookup,
    )

    # Recently watched titles for the hero-banner recommendations —
    # shares the Watch Progress UoW factory above.
    _watch_history_adapter = providers.Factory(
        WatchHistoryAdapter,
        watch_progress_uow_factory=_watch_progress_uow_factory_for_progress_lookup,
    )

    # Same pattern for the per-profile library ACL: built at the
    # composition root with its own identity UoW factory so the
    # Media container stays free of an Identity import.
    _identity_uow_factory_for_profile_library_access = providers.Singleton(
        SqlAlchemyIdentityUnitOfWorkFactory,
        session_factory=infrastructure.session_factory,
    )

    _profile_library_access_adapter = providers.Factory(
        ProfileLibraryAccessAdapter,
        identity_uow_factory=_identity_uow_factory_for_profile_library_access,
    )

    # Library UoW factory built at the composition root so the
    # Media container can read libraries (for the trigger-scan use
    # case) without the parent having to forward-reference the
    # Library container — which would create a parse-order cycle
    # (Library already depends on Media via the catalog repo).
    _library_uow_factory_for_media = providers.Singleton(
        SqlAlchemyLibraryUnitOfWorkFactory,
        session_factory=infrastructure.session_factory,
    )

    # Preferences UoW factory built at the composition root so Media can
    # read a profile's playback preference (ADR-026 — default audio at
    # /tracks) without forward-referencing the Preferences container.
    _preferences_uow_factory_for_media = providers.Singleton(
        SqlAlchemyPreferencesUnitOfWorkFactory,
        session_factory=infrastructure.session_factory,
    )

    # ADR-015 Phase 3: the auto-merge detector needs to ask "is
    # this file accessible?" and "is the library root mounted?"
    # before silently absorbing an orphan candidate. The adapter
    # combines a Library UoW lookup with raw pathlib.exists.
    _library_health_adapter = providers.Factory(
        LibraryHealthAdapter,
        library_uow_factory=_library_uow_factory_for_media,
    )

    # Real readiness probes that back ``GET /health/ready`` — see
    # ``src/infrastructure/health/probes.py``. Singletons because
    # the probes are stateless and the underlying deps
    # (session_factory, library UoW) are already shared singletons.
    database_probe = providers.Singleton(
        DatabaseProbe,
        session_factory=infrastructure.session_factory,
    )

    filesystem_probe = providers.Singleton(
        FilesystemProbe,
        library_uow_factory=_library_uow_factory_for_media,
    )

    # Settings BC (ADR-013): persistence + RuntimeSettings snapshot
    # facade. Declared before Media + Identity because both inject
    # ``runtime_settings`` for their consumers (HLS, ffmpeg helpers,
    # avatar storage).
    settings = providers.Container(
        SettingsContainer,
        session_factory=infrastructure.session_factory,
    )

    # Notifications is built before Catalog Requests so its publisher
    # adapter can be injected as the latter's ``NotificationPublisherPort``
    # — used by both the OnMediaEnriched fanout and the manual
    # "mark as included" action. Notifications takes no Catalog Requests
    # dependency, so the ordering stays acyclic.
    notifications = providers.Container(
        NotificationsContainer,
        session_factory=infrastructure.session_factory,
    )

    # Cross-BC title provider for Catalog Requests: built here (not in
    # MediaContainer) because Catalog Requests is composed before Media
    # — wiring it through the Media container would invert the build
    # order. A dedicated TMDB client keeps this independent of the
    # Media container's own ``tmdb_client``.
    _catalog_request_tmdb_client = providers.Singleton(
        TmdbClient,
        api_key=config.provided.tmdb_api_key,
        supported_locales=config.provided.supported_locales,
    )

    _localized_title_provider_adapter = providers.Singleton(
        TmdbLocalizedTitleAdapter,
        tmdb_client=_catalog_request_tmdb_client,
    )

    # Catalog Requests is built before Media so its ACL adapter can be
    # plumbed into the Media container as the ``CatalogRequestLookupPort``
    # implementation. Catalog Requests itself takes no Media dependency,
    # so the ordering is acyclic.
    catalog_requests = providers.Container(
        CatalogRequestsContainer,
        session_factory=infrastructure.session_factory,
        notification_publisher=notifications.notification_publisher,
        localized_title_provider=_localized_title_provider_adapter,
    )

    # Metadata / Enrichment provider BC (ADR-032): the TMDB gateway plus
    # artwork mirror storage/download and the pure person-bio lookup.
    # Composed before Media so Media's enrichment / relink / suggestion
    # use cases can consume its published ``tmdb_client`` provider via
    # cross-container wiring (the Core-depends-on-Supporting provider
    # contract). Metadata takes no dependency on other BCs.
    metadata = providers.Container(
        MetadataContainer,
        tmdb_api_key=config.provided.tmdb_api_key,
        supported_locales=config.provided.supported_locales,
        artwork_storage_directory=config.provided.artwork_storage_directory,
    )

    media = providers.Container(
        MediaContainer,
        session_factory=infrastructure.session_factory,
        event_bus=infrastructure.event_bus,
        progress_lookup=_progress_lookup_adapter,
        watch_history=_watch_history_adapter,
        profile_library_access=_profile_library_access_adapter,
        catalog_request_lookup=catalog_requests.catalog_request_lookup,
        library_uow_factory=_library_uow_factory_for_media,
        library_health=_library_health_adapter,
        identity_uow_factory=_identity_uow_factory_for_profile_library_access,
        preferences_uow_factory=_preferences_uow_factory_for_media,
        tmdb_client=metadata.tmdb_client,
        runtime_settings=settings.runtime_settings,
    )

    library = providers.Container(
        LibraryContainer,
        session_factory=infrastructure.session_factory,
        media_uow_factory=media.media_unit_of_work_factory,
    )

    # Streaming (ADR-032) composed after Media so its cross-BC catalog
    # lookup adapter reuses media's catalog use cases (preserving the
    # per-profile library ACL) via the MediaPlaybackLookupPort seam, and
    # its admin OCR source lookups read the media UoW directly.
    streaming = providers.Container(
        StreamingContainer,
        session_factory=infrastructure.session_factory,
        runtime_settings=settings.runtime_settings,
        hls_cache_directory=config.provided.hls_cache_directory,
        get_movie_by_id=media.get_movie_by_id,
        get_series_by_id=media.get_series_by_id,
        media_uow_factory=media.media_unit_of_work_factory,
        identity_uow_factory=_identity_uow_factory_for_profile_library_access,
        preferences_uow_factory=_preferences_uow_factory_for_media,
    )

    # Reverse seams (ADR-032): Media consumes three things now owned by the
    # Streaming BC — the shared ffprobe service (scan + segments), the
    # scrub-preview locator (scan re-link, via a media-side ACL adapter),
    # and the HLS cache-stats read port (admin overview, via a media-side
    # ACL adapter delegating to Streaming's use case). Wired by overriding
    # Media's placeholder Dependencies after StreamingContainer is composed
    # so the mutual Media<->Streaming wiring stays acyclic.
    media.media_probe_service.override(streaming.media_probe_service)
    media.scrub_preview_locator.override(
        providers.Factory(
            ScrubPreviewLocatorAdapter,
            locator=streaming.scrub_preview_locator,
        )
    )
    media.hls_cache_stats.override(
        providers.Factory(
            HlsCacheStatsAdapter,
            get_hls_cache_stats=streaming.get_hls_cache_stats,
        )
    )

    # Identity ships its container before the consumer BCs (watch_progress,
    # collections, preferences) so future PRs can inject ``profile_lookup``
    # via the ACL pattern without reordering the composition root.
    identity = providers.Container(
        IdentityContainer,
        session_factory=infrastructure.session_factory,
        event_bus=infrastructure.event_bus,
        thumbnails_directory=config.provided.thumbnails_directory,
        runtime_settings=settings.runtime_settings,
    )

    preferences = providers.Container(
        PreferencesContainer,
        session_factory=infrastructure.session_factory,
    )

    watch_progress = providers.Container(
        WatchProgressContainer,
        session_factory=infrastructure.session_factory,
        media_uow_factory=media.media_unit_of_work_factory,
    )

    collections = providers.Container(
        CollectionsContainer,
        session_factory=infrastructure.session_factory,
        media_uow_factory=media.media_unit_of_work_factory,
        watch_progress_uow_factory=watch_progress.watch_progress_unit_of_work_factory,
        identity_uow_factory=_identity_uow_factory_for_profile_library_access,
    )

    # =========================================================================
    # Cross-BC Services
    # =========================================================================
    # Wired at the composition root because it needs UoW factories from
    # two sibling containers (``library`` and ``media``).

    library_scan_scheduler = providers.Singleton(
        LibraryScanScheduler,
        library_uow_factory=library.library_unit_of_work_factory,
        scan_run_service=media.scan_run_service,
        runtime_settings=settings.runtime_settings,
        job_run_recorder=media.job_run_service,
    )

    # Read-only window into the live scheduler for the admin Jobs page.
    # Shares the same scheduler singleton the lifespan starts.
    scheduler_inspector = providers.Singleton(
        LibraryScanSchedulerInspector,
        scheduler=library_scan_scheduler,
    )

    list_jobs = providers.Factory(
        ListJobsUseCase,
        scheduler_inspector=scheduler_inspector,
        media_uow_factory=media.media_unit_of_work_factory,
    )

    # Write-side control of the same scheduler singleton for the admin
    # "run now" action.
    scheduler_controller = providers.Singleton(
        LibraryScanSchedulerController,
        scheduler=library_scan_scheduler,
    )

    trigger_job = providers.Factory(
        TriggerJobUseCase,
        scheduler_control=scheduler_controller,
    )

    thumbnail_backfill_job = providers.Singleton(
        ThumbnailBackfillJob,
        media_uow_factory=media.media_unit_of_work_factory,
        runtime_settings=settings.runtime_settings,
        thumbnail_service=streaming.thumbnail_generation_service,
    )

    artwork_mirror_job = providers.Singleton(
        ArtworkMirrorJob,
        media_uow_factory=media.media_unit_of_work_factory,
        runtime_settings=settings.runtime_settings,
        downloader=metadata.artwork_downloader,
        storage=metadata.artwork_storage,
    )

    intro_detection_job = providers.Singleton(
        IntroDetectionJob,
        media_uow_factory=media.media_unit_of_work_factory,
        intro_detectors=providers.Dict(
            {
                IntroDetectionAlgorithm.CHROMAPRINT: media.chromaprint_intro_detector,
                IntroDetectionAlgorithm.FRAME_HASH: media.frame_hash_intro_detector,
            },
        ),
        runtime_settings=settings.runtime_settings,
    )

    # Lives here rather than in MediaContainer because the operator
    # "detect now" path drives the same job singleton the scheduler
    # ticks, and that singleton is composed at this level.
    intro_detection_runner = providers.Singleton(
        BackgroundIntroDetectionRunner,
        job=intro_detection_job,
    )

    reset_season_intro_detection = providers.Factory(
        ResetSeasonIntroDetectionUseCase,
        uow_factory=media.media_unit_of_work_factory,
        detection_runner=intro_detection_runner,
    )

    credits_detection_job = providers.Singleton(
        CreditsDetectionJob,
        media_uow_factory=media.media_unit_of_work_factory,
        credits_detector=media.credits_detector,
        runtime_settings=settings.runtime_settings,
    )

    scan_dedup_sweep_job = providers.Singleton(
        ScanDedupSweepJob,
        sweep_use_case=media.sweep_movie_conflicts,
        runtime_settings=settings.runtime_settings,
    )

    subtitle_ocr_job = providers.Singleton(
        SubtitleOcrBackfillJob,
        media_uow_factory=media.media_unit_of_work_factory,
        streaming_uow_factory=streaming.streaming_unit_of_work_factory,
        runtime_settings=settings.runtime_settings,
        ocr_service=streaming.subtitle_ocr_service,
        probe_service=streaming.media_probe_service,
    )


# Convenience alias
Container = ApplicationContainer
