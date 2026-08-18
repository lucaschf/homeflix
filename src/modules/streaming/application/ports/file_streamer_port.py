"""Port for streaming raw file bytes (direct MP4/WebM playback)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class FileStreamerPort(ABC):
    """Read a file from disk in chunks suitable for HTTP streaming."""

    @abstractmethod
    def get_file_size(self, file_path: str) -> int:
        """Return the size of ``file_path`` in bytes."""
        ...

    @abstractmethod
    def stream_range(
        self,
        file_path: str,
        start: int,
        end: int,
    ) -> AsyncIterator[bytes]:
        """Yield bytes ``[start, end]`` (inclusive) in streaming chunks."""
        ...


__all__ = ["FileStreamerPort"]
