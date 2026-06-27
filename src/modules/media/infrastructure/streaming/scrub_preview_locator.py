"""Filesystem implementation of :class:`ScrubPreviewLocatorPort`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.modules.media.application.ports.scrub_preview_locator_port import (
    ScrubPreviewLocatorPort,
)
from src.modules.media.infrastructure.streaming.thumbnail_service import (
    SPRITE_FILENAME,
    VTT_FILENAME,
    scrub_preview_output_dir,
)

if TYPE_CHECKING:
    from src.modules.media.application.ports.runtime_config_ports import ThumbnailConfigPort


class FilesystemScrubPreviewLocator(ScrubPreviewLocatorPort):
    """Locate scrub previews on the local filesystem.

    Reads the configured sprite ``subdir`` from runtime settings on each
    call so an admin edit propagates without a restart, then checks the
    deterministic per-stem location (see ``scrub_preview_output_dir``)
    for both the VTT and its sprite.
    """

    def __init__(self, runtime_settings: ThumbnailConfigPort) -> None:
        self._runtime_settings = runtime_settings

    async def locate(self, source_file_path: str) -> str | None:
        """Return the VTT path when a complete preview is on disk, else ``None``."""
        subdir = (await self._runtime_settings.thumbnail_backfill()).subdir
        output_dir = scrub_preview_output_dir(Path(source_file_path), subdir)
        vtt = output_dir / VTT_FILENAME
        sprite = output_dir / SPRITE_FILENAME
        if vtt.is_file() and sprite.is_file():
            return str(vtt)
        return None


__all__ = ["FilesystemScrubPreviewLocator"]
