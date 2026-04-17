"""CreateCustomListUseCase - Create a new custom list."""

from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CreateCustomListInput,
    CustomListOutput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import MAX_LISTS, CustomList


class CreateCustomListUseCase:
    """Create a new user-defined custom list.

    Enforces the maximum list limit and unique name constraint.

    Example:
        >>> use_case = CreateCustomListUseCase(uow_factory)
        >>> result = await use_case.execute(CreateCustomListInput(name="Action Movies"))
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CreateCustomListInput) -> CustomListOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the list name.

        Returns:
            CustomListOutput with the created list data.

        Raises:
            BusinessRuleViolationException: If list limit reached or name already exists.
        """
        async with self._uow_factory() as uow:
            current_count = await uow.custom_lists.count()
            if current_count >= MAX_LISTS:
                raise BusinessRuleViolationException(
                    message=f"Cannot create more than {MAX_LISTS} custom lists",
                    message_code="CUSTOM_LIST_LIMIT_EXCEEDED",
                    rule_code="CUSTOM_LIST_LIMIT_EXCEEDED",
                )

            existing = await uow.custom_lists.find_by_name(input_dto.name.strip())
            if existing:
                raise BusinessRuleViolationException(
                    message=f"A list named '{input_dto.name.strip()}' already exists",
                    message_code="CUSTOM_LIST_NAME_DUPLICATE",
                    rule_code="CUSTOM_LIST_NAME_DUPLICATE",
                )

            custom_list = CustomList.create(name=input_dto.name)
            saved = await uow.custom_lists.add(custom_list)
        return CustomListOutput.from_entity(saved)


__all__ = ["CreateCustomListUseCase"]
