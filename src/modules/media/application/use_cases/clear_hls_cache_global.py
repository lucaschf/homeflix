"""ClearHlsCacheGlobalUseCase — wipe every cached HLS bucket."""

from src.modules.media.application.ports import HlsPlaylistPort


class ClearHlsCacheGlobalUseCase:
    """Discard the entire HLS cache.

    Distinct from :class:`ClearHlsCacheUseCase` which targets one
    source file: this is the admin "clean slate" affordance triggered
    from the System page, e.g. after the operator changes a transcode
    setting and wants every subsequent play to re-encode from scratch.

    The underlying port call also stamps the cache's last-cleared
    marker so :class:`GetHlsCacheStatsUseCase` can show *when* the
    cache was last wiped on the admin page.
    """

    def __init__(self, hls: HlsPlaylistPort) -> None:
        self._hls = hls

    def execute(self) -> None:
        """Clear every cached HLS file."""
        self._hls.clear_cache(None)


__all__ = ["ClearHlsCacheGlobalUseCase"]
