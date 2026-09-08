"""Derives and caches downscaled artwork variants (ADR-034).

The one place that decides how a ``?w=`` request is satisfied: a
stored variant is served as-is; otherwise the original is read,
downscaled through :class:`ArtworkResizerPort`, stored under the
variant key and served. The original is never upscaled and never
touched. When the original cannot be resized (corrupt, unsupported
format, storage hiccup) the original bytes are served exactly as the
route did before variants existed — a variant is an optimisation,
never a new way for an image to disappear.

Both the proxy route (lazy, for the already-mirrored catalog) and the
mirror job (eager, right after a new original lands) go through this
service, so the naming, the no-upscale rule and the single-flight
guard live here and nowhere else. Application-level policy over ports
(ADR-025); the adapters only report facts.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.metadata.application.ports.artwork_resizer_port import (
    UnsupportedArtworkImageError,
)
from src.modules.metadata.domain.value_objects.artwork_variant import ARTWORK_WIDTH_LADDER

if TYPE_CHECKING:
    from src.modules.metadata.application.ports.artwork_resizer_port import ArtworkResizerPort
    from src.modules.metadata.application.ports.artwork_storage_port import (
        ArtworkStoragePort,
        StoredArtwork,
    )
    from src.modules.metadata.domain.value_objects.artwork_key import ArtworkKey
    from src.modules.metadata.domain.value_objects.artwork_variant import (
        ArtworkKind,
        ArtworkWidth,
    )

_logger = get_logger()


class ArtworkVariantService:
    """Serve a mirrored artwork at a ladder width, deriving it on first use.

    Args:
        storage: Where originals live and variants are written.
        resizer: Produces the downscaled rendition.
    """

    def __init__(self, storage: ArtworkStoragePort, resizer: ArtworkResizerPort) -> None:
        self._storage = storage
        self._resizer = resizer
        # Single-flight per variant key: a burst of first requests for
        # the same variant (a hero backdrop on every open tab) resizes
        # once, the rest wait and read the stored result. Per process —
        # enough for the single-node deployment; a second process would
        # merely duplicate the work, never corrupt it (writes are atomic).
        self._locks: dict[str, asyncio.Lock] = {}

    async def open_original(self, key: ArtworkKey) -> StoredArtwork | None:
        """The untouched original, or ``None`` when it was never mirrored."""
        return await self._storage.open(str(key))

    async def ensure(self, key: ArtworkKey, width: ArtworkWidth) -> StoredArtwork | None:
        """Return ``key`` at ``width``, deriving and storing the variant if needed.

        Returns:
            The stored variant; the original when it is not wider than
            ``width`` or could not be resized; ``None`` when the original
            itself is missing from storage.
        """
        variant_key = str(key.variant(width))
        stored = await self._storage.open(variant_key)
        if stored is not None:
            return stored
        original = await self._storage.open(str(key))
        if original is None:
            return None

        lock = self._locks.setdefault(variant_key, asyncio.Lock())
        try:
            async with lock:
                # Whoever held the lock first may have stored it meanwhile.
                stored = await self._storage.open(variant_key)
                if stored is not None:
                    return stored
                return await self._derive(key, variant_key, width, original)
        finally:
            if not lock.locked():
                self._locks.pop(variant_key, None)

    async def pregenerate(
        self,
        key: ArtworkKey,
        kind: ArtworkKind,
        *,
        content: bytes,
        content_type: str,
    ) -> None:
        """Best-effort: store every ladder width of ``kind`` for a fresh original.

        Called by the mirror job with the bytes it just stored, so the
        first viewer never pays the resize. Widths the original is not
        wider than are skipped, and no failure propagates — the mirror
        itself has already succeeded.
        """
        for width in ARTWORK_WIDTH_LADDER[kind]:
            variant_key = str(key.variant(width))
            try:
                resized = await self._resizer.resize(content, width=width.value)
                if resized is None:
                    continue
                await self._storage.save(
                    content=resized.content, content_type=resized.content_type, key=variant_key
                )
            except (UnsupportedArtworkImageError, OSError) as exc:
                _logger.warning(
                    "[artwork-variants] pre-generation skipped",
                    key=str(key),
                    width=width.value,
                    content_type=content_type,
                    error=str(exc),
                )
                return

    async def _derive(
        self,
        key: ArtworkKey,
        variant_key: str,
        width: ArtworkWidth,
        original: StoredArtwork,
    ) -> StoredArtwork:
        """Resize + store ``original`` at ``width``; fall back to the original."""
        try:
            resized = await self._resizer.resize(original.content, width=width.value)
        except UnsupportedArtworkImageError as exc:
            _logger.warning(
                "[artwork-variants] original is not resizable; serving it as-is",
                key=str(key),
                width=width.value,
                error=str(exc),
            )
            return original
        if resized is None:
            return original
        try:
            await self._storage.save(
                content=resized.content, content_type=resized.content_type, key=variant_key
            )
        except OSError as exc:
            _logger.warning(
                "[artwork-variants] could not store variant; serving the original",
                key=str(key),
                width=width.value,
                error=str(exc),
            )
            return original
        stored = await self._storage.open(variant_key)
        return stored if stored is not None else original


__all__ = ["ArtworkVariantService"]
