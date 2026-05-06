"""AddItemToCustomListUseCase - Add a media item to a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import CustomListItem
from src.shared_kernel.value_objects.profile_id import ProfileId


class AddItemToCustomListUseCase:
    """Add a movie or series to a custom list owned by the caller's profile.

    Enforces the per-list item limit and prevents duplicates within the
    list.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: AddItemToCustomListInput) -> None:
        """Add the item, enforcing list ownership + limits."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            existing_item = await uow.custom_lists.find_item(
                input_dto.list_id, input_dto.media_id, profile_id
            )
            if existing_item:
                raise BusinessRuleViolationException(
                    message="Item already exists in this list",
                    message_code="CUSTOM_LIST_ITEM_DUPLICATE",
                    rule_code="CUSTOM_LIST_ITEM_DUPLICATE",
                )

            # Validate item limit via domain entity
            updated_list = custom_list.increment_item_count()

            next_position = await uow.custom_lists.get_next_position(input_dto.list_id, profile_id)

            item = CustomListItem.create(
                media_id=input_dto.media_id,
                media_type=input_dto.media_type,
                position=next_position,
            )

            await uow.custom_lists.add_item(input_dto.list_id, item, profile_id)
            await uow.custom_lists.update(updated_list)


__all__ = ["AddItemToCustomListUseCase"]
