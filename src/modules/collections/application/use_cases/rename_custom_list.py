"""RenameCustomListUseCase - Rename an existing custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    RenameCustomListInput,
)
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId


class RenameCustomListUseCase:
    """Rename an existing custom list owned by the caller's profile."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: RenameCustomListInput) -> CustomListOutput:
        """Rename the list, enforcing per-profile uniqueness."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            new_name = input_dto.name.strip()
            existing = await uow.custom_lists.find_by_name(new_name, profile_id)
            if existing and str(existing.id) != input_dto.list_id:
                raise BusinessRuleViolationException(
                    message=f"A list named '{new_name}' already exists",
                    message_code="CUSTOM_LIST_NAME_DUPLICATE",
                    rule_code="CUSTOM_LIST_NAME_DUPLICATE",
                )

            updated = custom_list.rename(new_name)
            saved = await uow.custom_lists.update(updated)
        return CustomListOutput.from_entity(saved)


__all__ = ["RenameCustomListUseCase"]
