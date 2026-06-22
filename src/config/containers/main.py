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
from src.config.containers.notifications import NotificationsContainer
from src.config.containers.preferences import PreferencesContainer
from src.config.containers.settings import SettingsContainer
from src.config.containers.watch_progress import WatchProgressContainer
from src.config.settings import Settings
from src.infrastructure.health import DatabaseProbe, FilesystemProbe
from src.infrastructure.scheduling import (
    CreditsDetectionJob,
    IntroDetectionJob,
    LibraryScanScheduler,
    ScanDedupSweepJob,
    ThumbnailBackfillJob,
)
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.modules.library.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyLibraryUnitOfWorkFactory,
)
from src.modules.media.application.use_cases.list_jobs import ListJobsUseCase
from src.modules.media.application.use_cases.trigger_job import TriggerJobUseCase
from src.modules.media.infrastructure.acl import (
    LibraryHealthAdapter,
    ProfileLibraryAccessAdapter,
    ProgressLookupAdapter,
)
from src.modules.media.infrastructure.scheduling.scheduler_controller import (
    LibraryScanSchedulerController,
)
from src.modules.media.infrastructure.scheduling.scheduler_inspector import (
    LibraryScanSchedulerInspector,
)
from src.modules.settings.domain.value_objects import IntroDetectionAlgorithm
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)


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

    # Catalog Requests is built before Media so its ACL adapter can be
    # plumbed into the Media container as the ``CatalogRequestLookupPort``
    # implementation. Catalog Requests itself takes no Media dependency,
    # so the ordering is acyclic.
    catalog_requests = providers.Container(
        CatalogRequestsContainer,
        session_factory=infrastructure.session_factory,
    )

    media = providers.Container(
        MediaContainer,
        session_factory=infrastructure.session_factory,
        event_bus=infrastructure.event_bus,
        progress_lookup=_progress_lookup_adapter,
        profile_library_access=_profile_library_access_adapter,
        catalog_request_lookup=catalog_requests.catalog_request_lookup,
        library_uow_factory=_library_uow_factory_for_media,
        library_health=_library_health_adapter,
        identity_uow_factory=_identity_uow_factory_for_profile_library_access,
        tmdb_api_key=config.provided.tmdb_api_key,
        hls_cache_directory=config.provided.hls_cache_directory,
        runtime_settings=settings.runtime_settings,
    )

    library = providers.Container(
        LibraryContainer,
        session_factory=infrastructure.session_factory,
        media_uow_factory=media.media_unit_of_work_factory,
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
    )

    # Notifications BC: provides the cross-BC publisher adapter
    # consumed by ``catalog_requests``' ``OnMediaEnrichedHandler``
    # (wired in main.py's event subscription block, not here, so the
    # container parse order stays acyclic).
    notifications = providers.Container(
        NotificationsContainer,
        session_factory=infrastructure.session_factory,
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
        thumbnail_service=media.thumbnail_generation_service,
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


# Convenience alias
Container = ApplicationContainer
