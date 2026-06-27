"""Adapter implementing ``LibraryLookupPort`` via the Library UoW.

This is the only Media file (besides the other ACL adapters) that
touches the Library BC for the scan flow. Above it, the scan route and
``TriggerScanUseCase`` see only the abstract port + ``LibraryRef`` DTO,
so the cross-BC boundary stays explicit (ADR-009).
"""

from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.media.application.ports.library_lookup_port import (
    LibraryLookupPort,
    LibraryRef,
)
from src.shared_kernel.value_objects.library_id import LibraryId


class LibraryLookupAdapter(LibraryLookupPort):
    """Resolve a :class:`LibraryRef` through the Library Unit of Work."""

    def __init__(self, library_uow_factory: LibraryUnitOfWorkFactory) -> None:
        self._library_uow_factory = library_uow_factory

    async def find(self, library_id: str) -> LibraryRef | None:
        """Load the library and project it to the scan-only ``LibraryRef``."""
        async with self._library_uow_factory() as uow:
            library = await uow.libraries.find_by_id(LibraryId(library_id))
        if library is None:
            return None
        return LibraryRef(id=str(library.id), paths=tuple(library.paths))


__all__ = ["LibraryLookupAdapter"]
