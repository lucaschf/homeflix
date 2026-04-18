"""Port for grouping related media files into variants.

The scan use case needs to detect that
``Inception.2010.1080p.BluRay.mkv`` and ``Inception.2010.4K.HDR.mkv``
belong to the same movie. The concrete implementation (parsing
filename tags) lives in ``media.infrastructure.file_system``; the
use case only depends on this port.
"""

from abc import ABC, abstractmethod
from collections import defaultdict


class VariantDetectorPort(ABC):
    """Group paths that represent the same content at different qualities.

    Implementations only need to provide ``extract_base_name``; the
    ``are_variants`` and ``group_variants`` defaults derive from it
    and rarely need overriding.
    """

    @abstractmethod
    def extract_base_name(self, file_path: str) -> str:
        """Strip quality-indicator tags and return the base content name."""
        ...

    def are_variants(self, file1: str, file2: str) -> bool:
        """Return ``True`` when two paths share the same base content name."""
        return self.extract_base_name(file1) == self.extract_base_name(file2)

    def group_variants(self, files: list[str]) -> dict[str, list[str]]:
        """Bucket paths by their base content name.

        Args:
            files: Paths to group.

        Returns:
            Map from base name to all paths that resolved to it.
        """
        groups: dict[str, list[str]] = defaultdict(list)
        for file_path in files:
            groups[self.extract_base_name(file_path)].append(file_path)
        return dict(groups)


__all__ = ["VariantDetectorPort"]
