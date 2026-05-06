"""Port for HLS playlist generation and cached file serving.

The HLS pipeline (ffmpeg spawning, segment caching, subtitle
extraction) lives in infrastructure. This port is the contract the
stream use cases depend on — thin enough that a future
implementation can swap ffmpeg for another encoder without touching
the application layer.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from src.modules.media.application.ports.media_probe_port import ProbeResult


class HlsPlaylistPort(ABC):
    """Manage the HLS cache: playlists, segments, subtitles, eviction."""

    @abstractmethod
    async def ensure_playlist(self, file_path: str) -> str:
        """Prepare an HLS cache for ``file_path`` and return its path hash.

        Blocks until at least the master playlist and the first segment
        are ready so the caller can serve the playlist immediately. The
        transcode always starts at the beginning of the source —
        resume positions are a player-side concern applied via
        ``HTMLMediaElement.currentTime`` once the manifest loads, which
        keeps a single cache bucket per file reusable across sessions.
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
    def clear_cache(self, file_path: str) -> None:
        """Discard the cache entry for ``file_path``."""
        ...


__all__ = ["HlsPlaylistPort"]
