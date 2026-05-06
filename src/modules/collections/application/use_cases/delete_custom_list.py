"""DeleteCustomListUseCase - Delete a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import DeleteCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId


class DeleteCustomListUseCase:
    """Delete a custom list (and its items) owned by the caller's profile."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: DeleteCustomListInput) -> None:
        """Soft-delete the list and its items, scoped to the caller's profile.

        Raises ``ResourceNotFoundException`` (HTTP 404) when the list
        either doesn't exist or doesn't belong to ``profile_id``;
        ownership leakage is impossible because the repository scopes
        every query.
        """
        async with self._uow_factory() as uow:
            removed = await uow.custom_lists.remove(
                input_dto.list_id, ProfileId(input_dto.profile_id)
            )
        if not removed:
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)


__all__ = ["DeleteCustomListUseCase"]
