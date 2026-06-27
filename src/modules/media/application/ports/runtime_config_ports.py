"""Protocol ports for reading runtime config buckets.

ADR-009-aligned (partial): these local Protocols invert the type
dependency so Media services no longer name the Settings BC's concrete
``RuntimeSettings`` infrastructure facade. Each Protocol describes only
the getter its consumer calls; ``RuntimeSettings`` satisfies them
structurally, so the composition root keeps injecting it unchanged and
the live snapshot/TTL behaviour is preserved.

This is the lighter "Protocol port (no adapter)" variant noted in ADR-009:
the return types are the Settings config value objects (stable published
contracts), not re-declared consumer-owned DTOs + an ACL adapter. Imported
under ``TYPE_CHECKING`` so the dependency stays annotation-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.modules.settings.domain.value_objects import (
        ScanDedupConfig,
        StreamingConfig,
        ThumbnailBackfillConfig,
    )


class StreamingConfigPort(Protocol):
    """Synchronous access to the current streaming-config snapshot."""

    def streaming_snapshot_sync(self) -> StreamingConfig:
        """Return the latest ``StreamingConfig`` without awaiting a refresh."""
        ...


class ThumbnailConfigPort(Protocol):
    """Access to the current thumbnail-backfill config."""

    async def thumbnail_backfill(self) -> ThumbnailBackfillConfig:
        """Return the current ``ThumbnailBackfillConfig``."""
        ...


class ScanDedupConfigPort(Protocol):
    """Access to the current scan-dedup config."""

    async def scan_dedup(self) -> ScanDedupConfig:
        """Return the current ``ScanDedupConfig``."""
        ...


__all__ = [
    "ScanDedupConfigPort",
    "StreamingConfigPort",
    "ThumbnailConfigPort",
]
