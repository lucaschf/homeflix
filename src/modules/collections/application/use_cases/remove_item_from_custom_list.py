"""RemoveItemFromCustomListUseCase - Remove a media item from a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RemoveItemFromCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory


class RemoveItemFromCustomListUseCase:
    """Remove a movie or series from a custom list."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: RemoveItemFromCustomListInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains list_id and media_id.

        Raises:
            ResourceNotFoundException: If the list or item does not exist.
        """
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            removed = await uow.custom_lists.remove_item(input_dto.list_id, input_dto.media_id)
            if not removed:
                raise ResourceNotFoundException.for_resource("CustomListItem", input_dto.media_id)

            updated_list = custom_list.decrement_item_count()
            await uow.custom_lists.update(updated_list)


__all__ = ["RemoveItemFromCustomListUseCase"]
