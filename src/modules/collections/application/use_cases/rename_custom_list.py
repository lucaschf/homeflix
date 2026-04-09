"""RenameCustomListUseCase - Rename an existing custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    RenameCustomListInput,
)
from src.modules.collections.domain.repositories import CustomListRepository


class RenameCustomListUseCase:
    """Rename an existing custom list.

    Enforces unique name constraint.

    Example:
        >>> use_case = RenameCustomListUseCase(custom_list_repository)
        >>> result = await use_case.execute(
        ...     RenameCustomListInput(list_id="lst_abc123", name="New Name"),
        ... )
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self, input_dto: RenameCustomListInput) -> CustomListOutput:
        """Execute the use case.

        Args:
            input_dto: Contains list_id and new name.

        Returns:
            CustomListOutput with the updated list data.

        Raises:
            ResourceNotFoundException: If the list does not exist.
            BusinessRuleViolationException: If the name is already taken.
        """
        custom_list = await self._repo.find_by_id(input_dto.list_id)
        if not custom_list:
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

        new_name = input_dto.name.strip()
        existing = await self._repo.find_by_name(new_name)
        if existing and str(existing.id) != input_dto.list_id:
            raise BusinessRuleViolationException(
                message=f"A list named '{new_name}' already exists",
                message_code="CUSTOM_LIST_NAME_DUPLICATE",
                rule_code="CUSTOM_LIST_NAME_DUPLICATE",
            )

        updated = custom_list.rename(new_name)
        saved = await self._repo.update(updated)
        return CustomListOutput.from_entity(saved)


__all__ = ["RenameCustomListUseCase"]
