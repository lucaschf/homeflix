"""ReorderCustomListItemsUseCase - Persist a manual item order."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import ReorderCustomListItemsInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ReorderCustomListItemsUseCase:
    """Persist a manual ordering of a custom list's items.

    The caller sends item media ids in the desired order — possibly not
    all of them: a profile under a maturity limit never sees the titles
    withheld from it, so it cannot send them. The repository keeps every
    unsent item in its slot, places the sent ones into the slots they
    occupy in the order given, ignores repeated and unknown ids, and
    renumbers the whole list ``0..n-1``. Sending every item once makes
    each ``position`` its index in the request.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ReorderCustomListItemsInput) -> None:
        """Reorder items in a list owned by the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            ordered = [CollectionMediaId(media_id) for media_id in input_dto.media_ids]
            await uow.custom_lists.reorder_items(input_dto.list_id, ordered, profile_id)


__all__ = ["ReorderCustomListItemsUseCase"]
