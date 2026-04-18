"""GetLibraryByIdUseCase."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import (
    GetLibraryByIdInput,
    LibraryOutput,
)
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases._counts import resolve_counts
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId


class GetLibraryByIdUseCase:
    """Fetch a single library by its external id."""

    def __init__(
        self,
        library_repository: LibraryRepository,
        media_count_query: MediaCountQueryPort,
    ) -> None:
        self._repo = library_repository
        self._media_count_query = media_count_query

    async def execute(self, input_dto: GetLibraryByIdInput) -> LibraryOutput:
        """Fetch a library or raise if not found.

        Args:
            input_dto: Carries the ``library_id``.

        Returns:
            The matching ``LibraryOutput``.

        Raises:
            ResourceNotFoundException: If the id doesn't match any
                non-deleted library.
        """
        library_id = LibraryId(input_dto.library_id)
        entity = await self._repo.find_by_id(library_id)
        if entity is None:
            raise ResourceNotFoundException.for_resource(
                "Library",
                input_dto.library_id,
            )
        movie_count, series_count = await resolve_counts(entity, self._media_count_query)
        return library_to_output(entity, movie_count=movie_count, series_count=series_count)


__all__ = ["GetLibraryByIdUseCase"]
