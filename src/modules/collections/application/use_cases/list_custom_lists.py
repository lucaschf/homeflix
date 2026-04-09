"""ListCustomListsUseCase - List all custom lists."""

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.domain.repositories import CustomListRepository


class ListCustomListsUseCase:
    """List all user-created custom lists.

    Example:
        >>> use_case = ListCustomListsUseCase(custom_list_repository)
        >>> lists = await use_case.execute()
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self) -> list[CustomListOutput]:
        """Execute the use case.

        Returns:
            List of CustomListOutput DTOs.
        """
        lists = await self._repo.list_all()
        return [CustomListOutput.from_entity(cl) for cl in lists]


__all__ = ["ListCustomListsUseCase"]
