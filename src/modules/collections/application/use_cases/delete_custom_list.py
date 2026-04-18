"""DeleteCustomListUseCase - Delete a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory


class DeleteCustomListUseCase:
    """Delete a custom list and all its items."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, list_id: str) -> None:
        """Execute the use case.

        Args:
            list_id: External ID of the list to delete.

        Raises:
            ResourceNotFoundException: If the list does not exist.
        """
        async with self._uow_factory() as uow:
            removed = await uow.custom_lists.remove(list_id)
        if not removed:
            raise ResourceNotFoundException.for_resource("CustomList", list_id)


__all__ = ["DeleteCustomListUseCase"]
