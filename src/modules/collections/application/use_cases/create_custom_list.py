"""CreateCustomListUseCase - Create a new custom list."""

from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CreateCustomListInput,
    CustomListOutput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId


class CreateCustomListUseCase:
    """Create a new user-defined custom list, scoped to one profile.

    Enforces the per-profile maximum list limit and unique-name
    constraint within the profile.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: CreateCustomListInput) -> CustomListOutput:
        """Create the list, enforcing per-profile limits and uniqueness."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            current_count = await uow.custom_lists.count(profile_id)
            # The factory enforces the MAX_LISTS limit (ADR-017).
            custom_list = CustomList.create(
                profile_id=profile_id,
                name=input_dto.name,
                existing_count=current_count,
                description=(input_dto.description or "").strip() or None,
            )

            existing = await uow.custom_lists.find_by_name(input_dto.name.strip(), profile_id)
            if existing:
                raise BusinessRuleViolationException(
                    message=f"A list named '{input_dto.name.strip()}' already exists",
                    message_code="CUSTOM_LIST_NAME_DUPLICATE",
                    rule_code="CUSTOM_LIST_NAME_DUPLICATE",
                )

            saved = await uow.custom_lists.add(custom_list)
        return CustomListOutput.from_entity(saved)


__all__ = ["CreateCustomListUseCase"]
