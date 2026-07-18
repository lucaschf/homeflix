"""Local-disk implementation of ``ArtworkStoragePort``.

Stores mirrored catalog artwork as plain files under a configured
directory and serves the bytes back through the API proxy route
(ADR-029). For a personal, single-node deployment this needs no extra
infrastructure — backing up the artwork is just copying the folder —
which is why it is the default backend over an object store.

The port stays backend-agnostic: a future S3 / MinIO adapter would
satisfy the same contract without touching callers. Filesystem I/O is
deferred to a worker thread via ``asyncio.to_thread`` — the same
pattern ``LocalAvatarStorage`` uses — so a slow disk never blocks the
event loop.
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from src.config.logging import get_logger
from src.modules.media.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)

_logger = get_logger()


class LocalArtworkStorage(ArtworkStoragePort):
    """Persist mirrored artwork as files under ``root_directory``.

    Keys are flat, storage-safe tokens ending in a file extension
    (e.g. ``ab12cd.jpg``) — the content type is derived from that
    extension on read, so no sidecar metadata is needed. The
    resolved path is confined to ``root_directory`` as defence in
    depth even though the route already validates the key charset.

    Args:
        root_directory: Directory that holds every artwork file. It
            (and any parents) is created on first write.
    """

    def __init__(self, *, root_directory: str) -> None:
        self._root = Path(root_directory)

    async def save(
        self,
        *,
        content: bytes,
        content_type: str,  # noqa: ARG002 — kept for port parity; local derives type from ext
        key: str,
    ) -> str:
        """Write ``content`` to ``{root}/{key}`` and return the proxy URL.

        ``content_type`` is accepted for contract parity with
        object-store backends but not persisted — it is re-derived
        from the key's extension on ``open``.
        """
        target = self._path_for(key)
        await asyncio.to_thread(self._write, target, content)
        return f"/api/v1/artwork/{key}"

    async def open(self, key: str) -> StoredArtwork | None:
        """Read the file back, or ``None`` when it does not exist."""
        target = self._path_for(key)
        data = await asyncio.to_thread(self._read, target)
        if data is None:
            return None
        return StoredArtwork(content=data, content_type=self._content_type(key))

    async def delete(self, key: str) -> None:
        """Remove the file. Idempotent — a missing file is a no-op."""
        target = self._path_for(key)
        try:
            await asyncio.to_thread(target.unlink)
        except FileNotFoundError:
            return
        except OSError as exc:
            _logger.warning(
                "[artwork-storage] failed to remove file",
                key=key,
                path=str(target),
                error=str(exc),
            )

    def _path_for(self, key: str) -> Path:
        """Resolve ``key`` under the root, rejecting any escape.

        The route already constrains keys to ``[A-Za-z0-9._-]+``; this
        containment check is belt-and-suspenders so a key like ``..``
        can never resolve outside the artwork directory.
        """
        root = self._root.resolve()
        target = (root / key).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"artwork key {key!r} escapes the storage root")
        return target

    @staticmethod
    def _write(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    @staticmethod
    def _read(target: Path) -> bytes | None:
        try:
            return target.read_bytes()
        except FileNotFoundError:
            return None

    @staticmethod
    def _content_type(key: str) -> str:
        """MIME type inferred from the key's file extension."""
        guessed, _ = mimetypes.guess_type(key)
        return guessed or "application/octet-stream"


__all__ = ["LocalArtworkStorage"]
