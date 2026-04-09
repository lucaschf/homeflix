"""AddItemToCustomListUseCase - Add a media item to a custom list."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
from src.modules.collections.domain.entities import CustomListItem
from src.modules.collections.domain.repositories import CustomListRepository


class AddItemToCustomListUseCase:
    """Add a movie or series to a custom list.

    Enforces item limit per list and prevents duplicates.

    Example:
        >>> use_case = AddItemToCustomListUseCase(custom_list_repository)
        >>> await use_case.execute(AddItemToCustomListInput(
        ...     list_id="lst_abc123",
        ...     media_id="mov_xyz789",
        ...     media_type="movie",
        ... ))
    """

    def __init__(self, custom_list_repository: CustomListRepository) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list persistence.
        """
        self._repo = custom_list_repository

    async def execute(self, input_dto: AddItemToCustomListInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains list_id, media_id, and media_type.

        Raises:
            ResourceNotFoundException: If the list does not exist.
            BusinessRuleViolationException: If item already in list or list is full.
        """
        custom_list = await self._repo.find_by_id(input_dto.list_id)
        if not custom_list:
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

        existing_item = await self._repo.find_item(input_dto.list_id, input_dto.media_id)
        if existing_item:
            raise BusinessRuleViolationException(
                message="Item already exists in this list",
                message_code="CUSTOM_LIST_ITEM_DUPLICATE",
                rule_code="CUSTOM_LIST_ITEM_DUPLICATE",
            )

        # Validate item limit via domain entity
        updated_list = custom_list.increment_item_count()

        next_position = await self._repo.get_next_position(input_dto.list_id)

        item = CustomListItem.create(
            media_id=input_dto.media_id,
            media_type=input_dto.media_type,
            position=next_position,
        )

        await self._repo.add_item(input_dto.list_id, item)
        await self._repo.update(updated_list)


__all__ = ["AddItemToCustomListUseCase"]
