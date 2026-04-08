"""DeleteCustomListUseCase - Delete a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.domain.repositories import CustomListRepository


class DeleteCustomListUseCase:
    """Delete a custom list and all its items.

    Example:
        >>> use_case = DeleteCustomListUseCase(custom_list_repository)
        >>> await use_case.execute("lst_abc123def456")
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self, list_id: str) -> None:
        """Execute the use case.

        Args:
            list_id: External ID of the list to delete.

        Raises:
            ResourceNotFoundException: If the list does not exist.
        """
        removed = await self._repo.remove(list_id)
        if not removed:
            raise ResourceNotFoundException.for_resource("CustomList", list_id)


__all__ = ["DeleteCustomListUseCase"]
