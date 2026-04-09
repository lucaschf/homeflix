"""RemoveItemFromCustomListUseCase - Remove a media item from a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RemoveItemFromCustomListInput
from src.modules.collections.domain.repositories import CustomListRepository


class RemoveItemFromCustomListUseCase:
    """Remove a movie or series from a custom list.

    Example:
        >>> use_case = RemoveItemFromCustomListUseCase(custom_list_repository)
        >>> await use_case.execute(RemoveItemFromCustomListInput(
        ...     list_id="lst_abc123",
        ...     media_id="mov_xyz789",
        ... ))
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self, input_dto: RemoveItemFromCustomListInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains list_id and media_id.

        Raises:
            ResourceNotFoundException: If the list or item does not exist.
        """
        custom_list = await self._repo.find_by_id(input_dto.list_id)
        if not custom_list:
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

        removed = await self._repo.remove_item(input_dto.list_id, input_dto.media_id)
        if not removed:
            raise ResourceNotFoundException.for_resource("CustomListItem", input_dto.media_id)

        updated_list = custom_list.decrement_item_count()
        await self._repo.update(updated_list)


__all__ = ["RemoveItemFromCustomListUseCase"]
