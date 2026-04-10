"""Tests for RemoveItemFromCustomListUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RemoveItemFromCustomListInput
from src.modules.collections.application.use_cases import (
    RemoveItemFromCustomListUseCase,
)
from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.repositories import CustomListRepository


@pytest.mark.unit
class TestRemoveItemFromCustomListUseCase:
    """Tests for removing items from custom lists."""

    @pytest.mark.asyncio
    async def test_should_remove_item_successfully(self) -> None:
        custom_list = CustomList.create(name="Test").with_updates(item_count=3)
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = True
        mock_repo.update.return_value = custom_list.decrement_item_count()
        use_case = RemoveItemFromCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(
            RemoveItemFromCustomListInput(
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
            )
        )

        mock_repo.remove_item.assert_called_once_with(str(custom_list.id), "mov_abc123def456")
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = None
        use_case = RemoveItemFromCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveItemFromCustomListInput(
                    list_id="lst_nonexistent00",
                    media_id="mov_abc123def456",
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_item_not_in_list(self) -> None:
        custom_list = CustomList.create(name="Test")
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = False
        use_case = RemoveItemFromCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveItemFromCustomListInput(
                    list_id=str(custom_list.id),
                    media_id="mov_notinlist0000",
                )
            )

        assert exc_info.value.resource_type == "CustomListItem"

    @pytest.mark.asyncio
    async def test_should_decrement_item_count_after_removal(self) -> None:
        custom_list = CustomList.create(name="Test").with_updates(item_count=5)
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = True
        mock_repo.update.return_value = custom_list.decrement_item_count()
        use_case = RemoveItemFromCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(
            RemoveItemFromCustomListInput(
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
            )
        )

        updated_list = mock_repo.update.call_args[0][0]
        assert updated_list.item_count == 4
