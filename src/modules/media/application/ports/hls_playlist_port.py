"""Port for HLS playlist generation and cached file serving.

The HLS pipeline (ffmpeg spawning, segment caching, subtitle
extraction) lives in infrastructure. This port is the contract the
stream use cases depend on — thin enough that a future
implementation can swap ffmpeg for another encoder without touching
the application layer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.modules.media.application.ports.media_probe_port import ProbeResult


@dataclass(frozen=True)
class HlsCacheStats:
    """Snapshot of HLS cache occupancy + configured limit.

    Used by the admin System page so the operator can eyeball how
    much disk the cache is sitting on relative to its ceiling, and
    when it was last cleared.

    Attributes:
        size_bytes: Bytes currently used on disk under the cache
            root (walk + sum, no per-bucket breakdown).
        max_bytes: Configured ceiling (from ``Settings``). The
            evictor enforces this; the admin page renders the
            ratio.
        last_cleared_at: Wallclock time of the last "clear all"
            invocation, or ``None`` when the cache hasn't been
            cleared globally since the marker started being kept.
    """

    size_bytes: int
    max_bytes: int
    last_cleared_at: datetime | None


class HlsPlaylistPort(ABC):
    """Manage the HLS cache: playlists, segments, subtitles, eviction."""

    @abstractmethod
    async def ensure_playlist(self, file_path: str, start: int = 0, end: int | None = None) -> str:
        """Prepare an HLS cache for ``file_path`` and return its path hash.

        Blocks until at least the master playlist and the first segment
        are ready so the caller can serve the playlist immediately.

        ``start`` is the source-time second the player wants playback
        to begin from. When non-zero, the implementation rounds it
        down to a coarser bucket (so a small change in resume position
        reuses the same encode) and spawns ffmpeg with an input seek
        to that bucket. The default of ``0`` preserves the
        single-bucket-per-file behaviour for cold first plays.

        ``end`` is the source-time second the encode is clamped to end
        at, for a title that occupies only a sub-range of a shared
        physical file (ADR-030). ``None`` (the default) encodes to the
        end of the file. It is folded into the returned path hash so
        distinct sub-ranges of one file cache independently.
        """
        ...

    @abstractmethod
    def get_master_playlist(self, path_hash: str) -> str | None:
        """Return the raw master ``m3u8`` for a cached path hash."""
        ...

    @abstractmethod
    def get_file_by_hash(self, path_hash: str, relative_path: str) -> Path | None:
        """Resolve a cached HLS file (segment, sub-playlist, VTT)."""
        ...

    @abstractmethod
    def wait_for_subtitle(self, path_hash: str, sub_index: int, timeout: float) -> bool:
        """Block until the given subtitle finishes extraction or ``timeout`` expires."""
        ...

    @abstractmethod
    def probe_tracks(self, file_path: str) -> ProbeResult:
        """Return track / resolution metadata, using the cached probe when available."""
        ...

    @abstractmethod
    def clear_cache(self, file_path: str | None) -> None:
        """Discard cache entries.

        A concrete ``file_path`` drops only that source file's buckets;
        passing ``None`` wipes the entire cache root (used by the
        admin "clean slate" affordance).
        """
        ...

    @abstractmethod
    def get_cache_stats(self) -> HlsCacheStats:
        """Return cache occupancy + configured limit + last clear time."""
        ...


__all__ = ["HlsCacheStats", "HlsPlaylistPort"]
