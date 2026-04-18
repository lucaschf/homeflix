"""Port for grouping related media files into variants.

The scan use case needs to detect that
``Inception.2010.1080p.BluRay.mkv`` and ``Inception.2010.4K.HDR.mkv``
belong to the same movie. The concrete implementation (parsing
filename tags) lives in ``media.infrastructure.file_system``; the
use case only depends on this port.
"""

from abc import ABC, abstractmethod


class VariantDetectorPort(ABC):
    """Group paths that represent the same content at different qualities."""

    @abstractmethod
    def extract_base_name(self, file_path: str) -> str:
        """Strip quality-indicator tags and return the base content name."""
        ...

    @abstractmethod
    def are_variants(self, file1: str, file2: str) -> bool:
        """Return ``True`` when two paths share the same base content name."""
        ...

    @abstractmethod
    def group_variants(self, files: list[str]) -> dict[str, list[str]]:
        """Bucket paths by their base content name.

        Args:
            files: Paths to group.

        Returns:
            Map from base name to all paths that resolved to it.
        """
        ...


__all__ = ["VariantDetectorPort"]
