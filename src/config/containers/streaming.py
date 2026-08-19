"""Dependency-injection container for the Streaming bounded context.

Owns the streaming subdomain's providers: direct file streaming, the HLS
pipeline (ffmpeg/probe/cache), the now-playing registry, thumbnail/scrub
generation, and the subtitle-OCR vertical (service + processor + audit
persistence). Catalog access is quarantined behind
:class:`MediaPlaybackLookupPort`, whose adapter is wired with media's
catalog use cases at the composition root so the per-profile library ACL
is preserved (ADR-009, ADR-032).
"""

from typing import Any

from dependency_injector import containers, providers

from src.modules.streaming.application.services.subtitle_ocr_processor import (
    SubtitleOcrProcessor,
)
from src.modules.streaming.application.use_cases.clear_hls_cache import ClearHlsCacheUseCase
from src.modules.streaming.application.use_cases.clear_hls_cache_global import (
    ClearHlsCacheGlobalUseCase,
)
from src.modules.streaming.application.use_cases.generate_hls_playlist import (
    GenerateHlsPlaylistUseCase,
)
from src.modules.streaming.application.use_cases.get_file_tracks import GetFileTracksUseCase
from src.modules.streaming.application.use_cases.get_hls_cache_stats import (
    GetHlsCacheStatsUseCase,
)
from src.modules.streaming.application.use_cases.get_now_playing import GetNowPlayingUseCase
from src.modules.streaming.application.use_cases.get_subtitle_ocr_run import (
    GetSubtitleOcrRunUseCase,
)
from src.modules.streaming.application.use_cases.list_subtitle_ocr_runs import (
    ListSubtitleOcrRunsUseCase,
)
from src.modules.streaming.application.use_cases.run_subtitle_ocr_for_media import (
    RunSubtitleOcrForMediaUseCase,
)
from src.modules.streaming.application.use_cases.serve_hls_file import ServeHlsFileUseCase
from src.modules.streaming.application.use_cases.stream_file_range import (
    StreamFileRangeUseCase,
)
from src.modules.streaming.infrastructure.acl.media_playback_lookup_adapter import (
    MediaPlaybackLookupAdapter,
)
from src.modules.streaming.infrastructure.acl.profile_playback_preference_adapter import (
    ProfilePlaybackPreferenceAdapter,
)
from src.modules.streaming.infrastructure.acl.profile_summary_adapter import (
    ProfileSummaryAdapter,
)
from src.modules.streaming.infrastructure.file_streamer import LocalFileStreamer
from src.modules.streaming.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyStreamingUnitOfWorkFactory,
)
from src.modules.streaming.infrastructure.streaming import (
    HlsService,
    MediaProbeService,
    TesseractPgsOcrService,
)
from src.modules.streaming.infrastructure.streaming.now_playing_registry import (
    NowPlayingRegistry,
)
from src.modules.streaming.infrastructure.streaming.scrub_preview_locator import (
    FilesystemScrubPreviewLocator,
)
from src.modules.streaming.infrastructure.streaming.thumbnail_service import (
    ThumbnailGenerationService,
)


class StreamingContainer(containers.DeclarativeContainer):
    """Container for Streaming bounded context dependencies.

    Cross-BC dependencies (the catalog lookup use cases + the media UoW
    factory) are wired from the parent :class:`ApplicationContainer`,
    which composes this container after ``MediaContainer``.
    """

    # -- Wired from the composition root --------------------------------------
    session_factory = providers.Dependency[Any]()
    runtime_settings = providers.Dependency[Any]()
    hls_cache_directory = providers.Dependency[str](default="./hls_cache")

    # Media catalog use cases + UoW factory (for the playback-lookup ACL).
    get_movie_by_id = providers.Dependency[Any]()
    get_series_by_id = providers.Dependency[Any]()
    media_uow_factory = providers.Dependency[Any]()

    # Identity + Preferences UoW factories for the now-playing "who" column
    # and the /tracks default-audio resolution (ADR-009 ACL adapters).
    identity_uow_factory = providers.Dependency[Any]()
    preferences_uow_factory = providers.Dependency[Any]()

    # -- Unit of Work ---------------------------------------------------------
    streaming_unit_of_work_factory = providers.Singleton(
        SqlAlchemyStreamingUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # -- Cross-BC ACL ---------------------------------------------------------
    media_playback_lookup = providers.Factory(
        MediaPlaybackLookupAdapter,
        get_movie_by_id=get_movie_by_id,
        get_series_by_id=get_series_by_id,
        media_uow_factory=media_uow_factory,
    )

    # Resolves watching profiles' display names via the identity UoW
    # (ADR-009 ACL), for the now-playing "who" column.
    profile_summary = providers.Singleton(
        ProfileSummaryAdapter,
        identity_uow_factory=identity_uow_factory,
    )

    # ADR-026: the /tracks use case reads the viewing profile's preferred
    # audio language from the Preferences BC to pick the default track.
    playback_preference = providers.Singleton(
        ProfilePlaybackPreferenceAdapter,
        preferences_uow_factory=preferences_uow_factory,
    )

    # -- Infrastructure -------------------------------------------------------
    media_probe_service = providers.Singleton(MediaProbeService)

    subtitle_ocr_service = providers.Singleton(TesseractPgsOcrService)

    hls_service = providers.Singleton(
        HlsService,
        runtime_settings=runtime_settings,
        cache_dir=hls_cache_directory,
        probe_service=media_probe_service,
        enable_eviction=True,
    )

    # In-memory registry of active playback sessions (admin now-playing).
    # Singleton — one ffmpeg fleet / cache, one source of truth. Written
    # by the streaming use cases (observationally), read by GetNowPlaying.
    now_playing_registry = providers.Singleton(NowPlayingRegistry)

    # Singleton because ``ThumbnailGenerationService`` is stateless apart
    # from the runtime config it reads per call; sharing one instance
    # across the eager fire-and-forget path (``hls_routes``) and the
    # periodic ``ThumbnailBackfillJob`` keeps configuration in one place.
    thumbnail_generation_service = providers.Singleton(
        ThumbnailGenerationService,
        runtime_settings=runtime_settings,
    )

    # Re-links scrub previews that already exist on disk (e.g. after a DB
    # reset) during a scan. Consumed by the Media scan flow through a
    # media-side ACL adapter wired at the composition root.
    scrub_preview_locator = providers.Singleton(
        FilesystemScrubPreviewLocator,
        runtime_settings=runtime_settings,
    )

    subtitle_ocr_processor = providers.Singleton(
        SubtitleOcrProcessor,
        probe_service=media_probe_service,
        ocr_service=subtitle_ocr_service,
    )

    # -- Direct byte-range streaming ------------------------------------------
    file_streamer = providers.Factory(LocalFileStreamer)

    stream_file_range = providers.Factory(
        StreamFileRangeUseCase,
        file_streamer=file_streamer,
    )

    # -- Use Cases — HLS + tracks + now-playing -------------------------------
    generate_hls_playlist = providers.Factory(
        GenerateHlsPlaylistUseCase,
        hls=hls_service,
        now_playing=now_playing_registry,
    )

    serve_hls_file = providers.Factory(
        ServeHlsFileUseCase,
        hls=hls_service,
        now_playing=now_playing_registry,
    )

    get_now_playing = providers.Factory(
        GetNowPlayingUseCase,
        now_playing=now_playing_registry,
        profile_summary=profile_summary,
    )

    get_file_tracks = providers.Factory(
        GetFileTracksUseCase,
        hls=hls_service,
        playback_preference=playback_preference,
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

    # -- Use Cases — Subtitle OCR ---------------------------------------------
    run_subtitle_ocr_for_media = providers.Factory(
        RunSubtitleOcrForMediaUseCase,
        media_lookup=media_playback_lookup,
        uow_factory=streaming_unit_of_work_factory,
        processor=subtitle_ocr_processor,
        ocr_service=subtitle_ocr_service,
        config=runtime_settings,
    )

    get_subtitle_ocr_run = providers.Factory(
        GetSubtitleOcrRunUseCase,
        uow_factory=streaming_unit_of_work_factory,
    )

    list_subtitle_ocr_runs = providers.Factory(
        ListSubtitleOcrRunsUseCase,
        uow_factory=streaming_unit_of_work_factory,
    )
