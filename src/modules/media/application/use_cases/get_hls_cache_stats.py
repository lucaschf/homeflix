"""GetHlsCacheStatsUseCase — admin survey of HLS cache occupancy."""

from src.modules.media.application.ports import HlsCacheStats, HlsPlaylistPort


class GetHlsCacheStatsUseCase:
    """Return the current HLS cache size + max + last-cleared.

    Used by the admin System page to render the occupancy bar and
    decide whether to surface a "running close to the limit" hint.
    Cheap — the underlying ``HlsService.get_cache_stats`` walks the
    cache root and sums file sizes; same shape ``evict_lru`` already
    runs per write.
    """

    def __init__(self, hls: HlsPlaylistPort) -> None:
        self._hls = hls

    def execute(self) -> HlsCacheStats:
        """Return the cache snapshot."""
        return self._hls.get_cache_stats()


__all__ = ["GetHlsCacheStatsUseCase"]
