"""Adapter satisfying media's ``HlsCacheStatsReadPort`` via streaming.

The admin Overview aggregator reads HLS cache occupancy through the
media-side port; this adapter is the single quarantined seam where Media
reaches into the Streaming BC (ADR-009), delegating to Streaming's
``GetHlsCacheStatsUseCase``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.ports.hls_cache_stats_read_port import (
    HlsCacheStatsReadPort,
    HlsCacheStatsView,
)

if TYPE_CHECKING:
    from src.modules.streaming.application.use_cases.get_hls_cache_stats import (
        GetHlsCacheStatsUseCase,
    )


class HlsCacheStatsAdapter(HlsCacheStatsReadPort):
    """Delegate cache-stats reads to Streaming's use case."""

    def __init__(self, get_hls_cache_stats: GetHlsCacheStatsUseCase) -> None:
        self._get_hls_cache_stats = get_hls_cache_stats

    def get_stats(self) -> HlsCacheStatsView:
        """Fetch the streaming cache snapshot and project it."""
        stats = self._get_hls_cache_stats.execute()
        return HlsCacheStatsView(
            size_bytes=stats.size_bytes,
            max_bytes=stats.max_bytes,
            last_cleared_at=stats.last_cleared_at,
        )


__all__ = ["HlsCacheStatsAdapter"]
