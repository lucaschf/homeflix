"""Port for locating an already-generated scrub-preview on disk."""

from abc import ABC, abstractmethod


class ScrubPreviewLocatorPort(ABC):
    """Resolve whether a media file's scrub-preview already exists on disk.

    The scrub-preview (sprite + WebVTT) is generated next to the source
    file at a deterministic, stem-based path. After a database reset the
    sprites usually survive on disk while the ``scrub_preview_path``
    column is cleared, so this port lets the scanner re-link an existing
    preview instead of waiting for the backfill job to regenerate it.
    """

    @abstractmethod
    async def locate(self, source_file_path: str) -> str | None:
        """Return the VTT path when a complete preview exists, else ``None``.

        A preview counts as complete only when BOTH the WebVTT cue file
        and its sibling sprite image are present, since the player needs
        both to render hover thumbnails.

        Args:
            source_file_path: Absolute path to the source media file.

        Returns:
            Absolute path to the ``sprite.vtt`` file, or ``None`` when no
            complete preview is on disk.
        """
        raise NotImplementedError


__all__ = ["ScrubPreviewLocatorPort"]
