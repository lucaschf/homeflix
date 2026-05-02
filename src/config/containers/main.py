"""Main application container.

Composes all sub-containers into a single container that serves
as the composition root for the application.

See ADR-004 for the rationale behind this design.
"""

from dependency_injector import containers, providers

from src.config.containers.catalog_requests import CatalogRequestsContainer
from src.config.containers.collections import CollectionsContainer
from src.config.containers.infrastructure import InfrastructureContainer
from src.config.containers.library import LibraryContainer
from src.config.containers.media import MediaContainer
from src.config.containers.preferences import PreferencesContainer
from src.config.containers.watch_progress import WatchProgressContainer
from src.config.settings import Settings
from src.infrastructure.scheduling import (
    IntroDetectionJob,
    LibraryScanScheduler,
    ThumbnailBackfillJob,
)
from src.modules.media.infrastructure.acl import ProgressLookupAdapter
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
        catalog_request_lookup=catalog_requests.catalog_request_lookup,
        tmdb_api_key=config.provided.tmdb_api_key,
        hls_cache_directory=config.provided.hls_cache_directory,
        hls_cache_max_size_mb=config.provided.hls_cache_max_size_mb,
        ffmpeg_threads=config.provided.ffmpeg_threads,
        intro_detection_max_hash_hamming=config.provided.intro_detection_max_hash_hamming,
        intro_detection_tolerance_hashes=config.provided.intro_detection_tolerance_hashes,
        intro_detection_min_intro_seconds=config.provided.intro_detection_min_intro_seconds,
        intro_detection_max_intro_seconds=config.provided.intro_detection_max_intro_seconds,
    )

    library = providers.Container(
        LibraryContainer,
        session_factory=infrastructure.session_factory,
        media_uow_factory=media.media_unit_of_work_factory,
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

    # =========================================================================
    # Cross-BC Services
    # =========================================================================
    # Wired at the composition root because it needs UoW factories from
    # two sibling containers (``library`` and ``media``).

    library_scan_scheduler = providers.Singleton(
        LibraryScanScheduler,
        library_uow_factory=library.library_unit_of_work_factory,
        media_uow_factory=media.media_unit_of_work_factory,
        file_scanner=infrastructure.file_scanner,
        variant_detector=infrastructure.variant_detector,
        event_bus=infrastructure.event_bus,
        reconcile_interval_minutes=config.provided.scheduler_reconcile_interval_minutes,
        probe_service=media.media_probe_service,
    )

    thumbnail_backfill_job = providers.Singleton(
        ThumbnailBackfillJob,
        media_uow_factory=media.media_unit_of_work_factory,
        thumbnail_service=media.thumbnail_generation_service,
        batch_size=config.provided.thumbnail_backfill_batch_size,
        sprite_subdir=config.provided.thumbnail_backfill_subdir,
    )

    intro_detection_job = providers.Singleton(
        IntroDetectionJob,
        media_uow_factory=media.media_unit_of_work_factory,
        audio_extractor=media.audio_extractor,
        chromaprint_service=media.chromaprint_service,
        intro_detector=media.intro_detector,
        batch_size=config.provided.intro_detection_batch_size,
        audio_window_seconds=config.provided.intro_detection_audio_window_seconds,
        min_confidence=config.provided.intro_detection_min_confidence,
    )


# Convenience alias
Container = ApplicationContainer
