"""Tests for AddItemToCustomListUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
from src.modules.collections.application.use_cases import AddItemToCustomListUseCase
from src.modules.collections.domain.entities import (
    MAX_ITEMS_PER_LIST,
    CustomList,
    CustomListItem,
)
from src.modules.collections.domain.repositories import CustomListRepository
from src.shared_kernel.value_objects import CollectionMediaType


def _create_list(name: str = "Test List", item_count: int = 0) -> CustomList:
    return CustomList.create(name=name).with_updates(item_count=item_count)


@pytest.mark.unit
class TestAddItemToCustomListUseCase:
    """Tests for adding items to custom lists."""

    @pytest.mark.asyncio
    async def test_should_add_item_successfully(self) -> None:
        custom_list = _create_list()
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        mock_repo.get_next_position.return_value = 0
        mock_repo.add_item.return_value = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
            position=0,
        )
        mock_repo.update.return_value = custom_list.increment_item_count()
        use_case = AddItemToCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(
            AddItemToCustomListInput(
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
            )
        )

        mock_repo.add_item.assert_called_once()
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = None
        use_case = AddItemToCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    list_id="lst_nonexistent00",
                    media_id="mov_abc123def456",
                    media_type=CollectionMediaType.MOVIE,
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_item_already_in_list(self) -> None:
        custom_list = _create_list(item_count=1)
        existing_item = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = existing_item
        use_case = AddItemToCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    list_id=str(custom_list.id),
                    media_id="mov_abc123def456",
                    media_type=CollectionMediaType.MOVIE,
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_DUPLICATE"

    @pytest.mark.asyncio
    async def test_should_raise_when_list_is_full(self) -> None:
        custom_list = _create_list(item_count=MAX_ITEMS_PER_LIST)
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        use_case = AddItemToCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    list_id=str(custom_list.id),
                    media_id="mov_abc123def456",
                    media_type=CollectionMediaType.MOVIE,
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_should_use_next_position(self) -> None:
        custom_list = _create_list(item_count=3)
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        mock_repo.get_next_position.return_value = 3
        mock_repo.add_item.return_value = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
            position=3,
        )
        mock_repo.update.return_value = custom_list.increment_item_count()
        use_case = AddItemToCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(
            AddItemToCustomListInput(
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
            )
        )

        mock_repo.get_next_position.assert_called_once_with(str(custom_list.id))
