"""Adapter satisfying media's ``ScrubPreviewLocatorPort`` via streaming.

The scan use case (Media BC) re-links an already-generated scrub-preview
so a database reset doesn't force a full backfill regeneration. The
concrete filesystem locator now lives in the Streaming BC; this adapter
is the single quarantined seam where Media reaches into Streaming
(ADR-009), keeping the scan use case dependent only on the media-side
port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.ports.scrub_preview_locator_port import (
    ScrubPreviewLocatorPort,
)

if TYPE_CHECKING:
    from src.modules.streaming.infrastructure.streaming.scrub_preview_locator import (
        FilesystemScrubPreviewLocator,
    )


class ScrubPreviewLocatorAdapter(ScrubPreviewLocatorPort):
    """Delegate scrub-preview lookups to the Streaming filesystem locator."""

    def __init__(self, locator: FilesystemScrubPreviewLocator) -> None:
        self._locator = locator

    async def locate(self, source_file_path: str) -> str | None:
        """Return the VTT path when a complete preview exists, else ``None``."""
        return await self._locator.locate(source_file_path)


__all__ = ["ScrubPreviewLocatorAdapter"]
