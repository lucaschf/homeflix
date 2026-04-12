"""DeleteLibraryUseCase."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import DeleteLibraryInput
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.library.domain.value_objects.library_id import LibraryId


class DeleteLibraryUseCase:
    """Soft-delete a library."""

    def __init__(self, library_repository: LibraryRepository) -> None:
        self._repo = library_repository

    async def execute(self, input_dto: DeleteLibraryInput) -> None:
        """Soft-delete a library by id.

        Args:
            input_dto: Carries the ``library_id``.

        Raises:
            ResourceNotFoundException: If no non-deleted library
                matches the id.
        """
        library_id = LibraryId(input_dto.library_id)
        deleted = await self._repo.delete(library_id)
        if not deleted:
            raise ResourceNotFoundException.for_resource(
                "Library",
                input_dto.library_id,
            )


__all__ = ["DeleteLibraryUseCase"]
