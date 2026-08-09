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
        """Soft-delete the list, its items, and any follows of it.

        Dropping follows in the same transaction keeps a shared list's
        deletion clean: followers lose the follow so the list vanishes
        from their surface with no dangling read (spec edge case 1).

        Raises ``ResourceNotFoundException`` (HTTP 404) when the list
        either doesn't exist or doesn't belong to ``profile_id``;
        ownership leakage is impossible because the repository scopes
        every query.
        """
        list_id = input_dto.list_id
        async with self._uow_factory() as uow:
            found = await uow.custom_lists.find_by_id(list_id, ProfileId(input_dto.profile_id))
            if found is None or found.id is None:
                raise ResourceNotFoundException.for_resource("CustomList", list_id)
            await uow.custom_lists.remove(list_id, ProfileId(input_dto.profile_id))
            await uow.list_follows.remove_all_for_list(found.id)


__all__ = ["DeleteCustomListUseCase"]
