"""Use case: per-library catalog disk usage for the admin Overview.

Sums primary-file bytes for movies and episodes grouped by library — a
cheap SQL aggregation (no disk walk). The result ranks libraries against
each other on the "Uso de disco por library" panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.dtos.library_usage_dtos import (
    LibraryUsageEntry,
    LibraryUsageOutput,
)

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class GetLibraryUsageUseCase:
    """Aggregate catalog size per library."""

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> LibraryUsageOutput:
        """Return per-library catalog size, largest first, plus the total."""
        async with self._uow_factory() as uow:
            movie_sizes = await uow.movies.total_file_size_by_library()
            episode_sizes = await uow.series.episode_file_size_by_library()

        merged: dict[str, int] = {}
        for sizes in (movie_sizes, episode_sizes):
            for library_id, size in sizes.items():
                merged[library_id] = merged.get(library_id, 0) + size

        entries = sorted(
            (
                LibraryUsageEntry(library_id=library_id, size_bytes=size)
                for library_id, size in merged.items()
            ),
            key=lambda entry: entry.size_bytes,
            reverse=True,
        )
        total = sum(entry.size_bytes for entry in entries)
        return LibraryUsageOutput(libraries=entries, total_bytes=total)
