"""RemoveItemFromCustomListUseCase - Remove a media item from a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RemoveItemFromCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class RemoveItemFromCustomListUseCase:
    """Remove a movie or series from a custom list owned by the caller."""

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: RemoveItemFromCustomListInput) -> None:
        """Soft-delete the item from a list owned by the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            removed = await uow.custom_lists.remove_item(
                input_dto.list_id, CollectionMediaId(input_dto.media_id), profile_id
            )
            if not removed:
                raise ResourceNotFoundException.for_resource("CustomListItem", input_dto.media_id)

            updated_list = custom_list.decrement_item_count()
            await uow.custom_lists.update(updated_list)


__all__ = ["RemoveItemFromCustomListUseCase"]
