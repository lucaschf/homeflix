"""Dependency-injection container for the Streaming bounded context.

Holds the streaming subdomain's own providers (direct file streaming for
now; HLS/probe/OCR migrate in later Strangler-Fig slices). Catalog access
is quarantined behind :class:`MediaPlaybackLookupPort`, whose adapter is
wired with media's catalog use cases at the composition root so the
per-profile library ACL is preserved (ADR-009, ADR-032 slice 4.1).
"""

from typing import Any

from dependency_injector import containers, providers

from src.modules.streaming.application.use_cases.stream_file_range import (
    StreamFileRangeUseCase,
)
from src.modules.streaming.infrastructure.acl.media_playback_lookup_adapter import (
    MediaPlaybackLookupAdapter,
)
from src.modules.streaming.infrastructure.file_streamer import LocalFileStreamer


class StreamingContainer(containers.DeclarativeContainer):
    """Container for Streaming bounded context dependencies.

    Cross-BC dependencies (the catalog lookup use cases) are wired from the
    parent :class:`ApplicationContainer`, which composes this container
    after ``MediaContainer``.
    """

    # Wired from the composition root with media's catalog use case
    # providers (``media.get_movie_by_id`` / ``media.get_series_by_id``).
    get_movie_by_id = providers.Dependency[Any]()
    get_series_by_id = providers.Dependency[Any]()

    # -- Cross-BC ACL ----------------------------------------------------------
    media_playback_lookup = providers.Factory(
        MediaPlaybackLookupAdapter,
        get_movie_by_id=get_movie_by_id,
        get_series_by_id=get_series_by_id,
    )

    # -- Direct byte-range streaming ------------------------------------------
    file_streamer = providers.Factory(LocalFileStreamer)

    stream_file_range = providers.Factory(
        StreamFileRangeUseCase,
        file_streamer=file_streamer,
    )
