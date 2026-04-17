"""DeleteLibraryUseCase."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.library.application.dtos.library_dtos import DeleteLibraryInput
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.library.domain.value_objects.library_id import LibraryId


class DeleteLibraryUseCase:
    """Soft-delete a library."""

    def __init__(self, uow_factory: LibraryUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: DeleteLibraryInput) -> None:
        """Soft-delete a library by id.

        Args:
            input_dto: Carries the ``library_id``.

        Raises:
            ResourceNotFoundException: If no non-deleted library
                matches the id.
        """
        library_id = LibraryId(input_dto.library_id)
        async with self._uow_factory() as uow:
            deleted = await uow.libraries.delete(library_id)

        if not deleted:
            raise ResourceNotFoundException.for_resource(
                "Library",
                input_dto.library_id,
            )


__all__ = ["DeleteLibraryUseCase"]
