"""ListCustomListsUseCase - List custom lists for a profile."""

from dataclasses import dataclass

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId


@dataclass(frozen=True)
class ListCustomListsInput:
    """Input for ListCustomListsUseCase."""

    profile_id: str


class ListCustomListsUseCase:
    """List all custom lists owned by the caller's profile."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListCustomListsInput) -> list[CustomListOutput]:
        """Return the profile's lists ordered by most recently updated."""
        async with self._uow_factory() as uow:
            lists = await uow.custom_lists.list_all(ProfileId(input_dto.profile_id))
        return [CustomListOutput.from_entity(cl) for cl in lists]


__all__ = ["ListCustomListsInput", "ListCustomListsUseCase"]
