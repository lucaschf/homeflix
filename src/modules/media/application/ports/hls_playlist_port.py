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
    async def ensure_playlist(self, file_path: str, start_seconds: float = 0.0) -> str:
        """Prepare an HLS cache for ``file_path`` and return its path hash.

        Blocks until at least the master playlist and the first few
        segments are ready so the caller can serve the playlist
        immediately. ``start_seconds > 0`` seeks the source before
        encoding (resume mid-file).
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
        """Discard every cache entry tied to ``file_path`` (all seek offsets)."""
        ...


__all__ = ["HlsPlaylistPort"]
