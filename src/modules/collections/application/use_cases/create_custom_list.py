"""CreateCustomListUseCase - Create a new custom list."""

from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CreateCustomListInput,
    CustomListOutput,
)
from src.modules.collections.domain.entities import MAX_LISTS, CustomList
from src.modules.collections.domain.repositories import CustomListRepository


class CreateCustomListUseCase:
    """Create a new user-defined custom list.

    Enforces the maximum list limit and unique name constraint.

    Example:
        >>> use_case = CreateCustomListUseCase(custom_list_repository)
        >>> result = await use_case.execute(CreateCustomListInput(name="Action Movies"))
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self, input_dto: CreateCustomListInput) -> CustomListOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the list name.

        Returns:
            CustomListOutput with the created list data.

        Raises:
            BusinessRuleViolationException: If list limit reached or name already exists.
        """
        current_count = await self._repo.count()
        if current_count >= MAX_LISTS:
            raise BusinessRuleViolationException(
                message=f"Cannot create more than {MAX_LISTS} custom lists",
                message_code="CUSTOM_LIST_LIMIT_EXCEEDED",
                rule_code="CUSTOM_LIST_LIMIT_EXCEEDED",
            )

        existing = await self._repo.find_by_name(input_dto.name.strip())
        if existing:
            raise BusinessRuleViolationException(
                message=f"A list named '{input_dto.name.strip()}' already exists",
                message_code="CUSTOM_LIST_NAME_DUPLICATE",
                rule_code="CUSTOM_LIST_NAME_DUPLICATE",
            )

        custom_list = CustomList.create(name=input_dto.name)
        saved = await self._repo.add(custom_list)
        return CustomListOutput.from_entity(saved)


__all__ = ["CreateCustomListUseCase"]
