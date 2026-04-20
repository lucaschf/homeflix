"""ListCustomListsUseCase - List all custom lists."""

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory


class ListCustomListsUseCase:
    """List all user-created custom lists.

    Example:
        >>> use_case = ListCustomListsUseCase(uow_factory)
        >>> lists = await use_case.execute()
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self) -> list[CustomListOutput]:
        """Execute the use case.

        Returns:
            List of CustomListOutput DTOs.
        """
        async with self._uow_factory() as uow:
            lists = await uow.custom_lists.list_all()
        return [CustomListOutput.from_entity(cl) for cl in lists]


__all__ = ["ListCustomListsUseCase"]
