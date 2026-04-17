"""AddItemToCustomListUseCase - Add a media item to a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.modules.collections.domain.entities import CustomListItem


class AddItemToCustomListUseCase:
    """Add a movie or series to a custom list.

    Enforces item limit per list and prevents duplicates.
    """

    def __init__(self, uow_factory: CollectionsUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: AddItemToCustomListInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains list_id, media_id, and media_type.

        Raises:
            ResourceNotFoundException: If the list does not exist.
            BusinessRuleViolationException: If item already in list or list is full.
        """
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            existing_item = await uow.custom_lists.find_item(
                input_dto.list_id, input_dto.media_id
            )
            if existing_item:
                raise BusinessRuleViolationException(
                    message="Item already exists in this list",
                    message_code="CUSTOM_LIST_ITEM_DUPLICATE",
                    rule_code="CUSTOM_LIST_ITEM_DUPLICATE",
                )

            # Validate item limit via domain entity
            updated_list = custom_list.increment_item_count()

            next_position = await uow.custom_lists.get_next_position(input_dto.list_id)

            item = CustomListItem.create(
                media_id=input_dto.media_id,
                media_type=input_dto.media_type,
                position=next_position,
            )

            await uow.custom_lists.add_item(input_dto.list_id, item)
            await uow.custom_lists.update(updated_list)


__all__ = ["AddItemToCustomListUseCase"]
