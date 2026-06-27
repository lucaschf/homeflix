"""Port for resolving a library's scan inputs from the Library BC.

The scan flow (route + ``TriggerScanUseCase``) only needs to confirm a
library exists and read the paths to scan — not the whole ``Library``
aggregate. This port exposes that minimal read as a consumer-owned DTO,
so Media never imports the Library aggregate or its Unit of Work (ADR-009).
The adapter lives in ``media.infrastructure.acl``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.shared_kernel.value_objects.file_path import FilePath


@dataclass(frozen=True)
class LibraryRef:
    """Minimal projection of a library for the scan flow.

    Attributes:
        id: Prefixed external id (``lib_xxx``) of the library.
        paths: Filesystem roots to scan. ``FilePath`` is a shared-kernel
            value object, so carrying it across the boundary does not
            couple Media to the Library aggregate.
    """

    id: str
    paths: tuple[FilePath, ...]


class LibraryLookupPort(ABC):
    """Read a library's scan inputs without touching the Library aggregate."""

    @abstractmethod
    async def find(self, library_id: str) -> LibraryRef | None:
        """Return the library's scan projection, or ``None`` if absent.

        Args:
            library_id: Prefixed external id (``lib_xxx``).

        Returns:
            A :class:`LibraryRef`, or ``None`` when no such library
            exists (the caller turns that into a 404 / domain error).
        """
        ...


__all__ = ["LibraryLookupPort", "LibraryRef"]
