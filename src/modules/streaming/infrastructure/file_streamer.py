"""Filesystem-backed ``FileStreamerPort`` implementation."""

from collections.abc import AsyncIterator
from pathlib import Path

from src.modules.streaming.application.ports.file_streamer_port import FileStreamerPort

_CHUNK_SIZE = 1024 * 1024  # 1 MB — matches the previous in-route size.


class LocalFileStreamer(FileStreamerPort):
    """Read bytes from local disk in chunks.

    The read loop stays synchronous under the hood — FastAPI runs the
    generator on a worker thread for streaming responses, so wrapping
    the `open()` in ``aiofiles`` would only add overhead.
    """

    def get_file_size(self, file_path: str) -> int:
        """Return the size of ``file_path`` in bytes."""
        return Path(file_path).stat().st_size

    async def stream_range(
        self,
        file_path: str,
        start: int,
        end: int,
    ) -> AsyncIterator[bytes]:
        """Yield bytes ``[start, end]`` (inclusive) in ``_CHUNK_SIZE`` chunks."""
        with Path(file_path).open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(_CHUNK_SIZE, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data


__all__ = ["LocalFileStreamer"]
