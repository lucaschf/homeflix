"""Adapter implementing ``LibraryHealthPort`` via the library UoW + pathlib.

This is the only file in the Media BC that combines the Library BC
(for ``Library.paths`` lookup) with raw filesystem checks. Above the
adapter, the use cases only see the abstract port — the cross-BC +
I/O boundaries stay explicit, per ADR-009.
"""

from pathlib import Path

from src.modules.library.application.unit_of_work import (
    LibraryUnitOfWorkFactory,
)
from src.modules.library.domain.value_objects.library_id import LibraryId
from src.modules.media.application.ports.library_health_port import (
    LibraryHealthPort,
)


class LibraryHealthAdapter(LibraryHealthPort):
    """Resolve filesystem health via the Library UoW + ``pathlib``."""

    def __init__(self, library_uow_factory: LibraryUnitOfWorkFactory) -> None:
        self._library_uow_factory = library_uow_factory

    async def is_file_accessible(self, file_path: str) -> bool:
        """Return ``Path(file_path).exists()`` without touching the UoW."""
        return Path(file_path).exists()

    async def is_library_root_accessible(self, library_id: str) -> bool:
        """Confirm every declared library root currently mounts.

        Missing libraries (deleted, never seeded) also return
        ``False`` — the caller's intent is "can I trust a
        file-missing signal for media inside this library?" and the
        safer answer for a phantom library is "no, fall back to the
        manual queue".
        """
        async with self._library_uow_factory() as uow:
            library = await uow.libraries.find_by_id(LibraryId(library_id))
        if library is None:
            return False
        # Partial-mount = unhealthy. The scanner cannot give the
        # operator a complete view, so treating "some roots mounted"
        # as healthy would risk auto-merging entities whose file
        # actually still lives on the missing root.
        return all(Path(p.value).exists() for p in library.paths)


__all__ = ["LibraryHealthAdapter"]
