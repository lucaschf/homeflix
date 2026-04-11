"""Tests for RenameCustomListUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    RenameCustomListInput,
)
from src.modules.collections.application.use_cases import RenameCustomListUseCase
from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.repositories import CustomListRepository


@pytest.mark.unit
class TestRenameCustomListUseCase:
    """Tests for renaming custom lists."""

    @pytest.mark.asyncio
    async def test_should_rename_successfully(self) -> None:
        custom_list = CustomList.create(name="Old Name")
        renamed = custom_list.rename("New Name")
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = None
        mock_repo.update.return_value = renamed
        use_case = RenameCustomListUseCase(custom_list_repository=mock_repo)

        result = await use_case.execute(
            RenameCustomListInput(list_id=str(custom_list.id), name="New Name")
        )

        assert isinstance(result, CustomListOutput)
        assert result.name == "New Name"
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = None
        use_case = RenameCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(list_id="lst_nonexistent00", name="New Name")
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_name_taken_by_other_list(self) -> None:
        custom_list = CustomList.create(name="My List")
        other_list = CustomList.create(name="Taken Name")
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = other_list
        use_case = RenameCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(list_id=str(custom_list.id), name="Taken Name")
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_NAME_DUPLICATE"

    @pytest.mark.asyncio
    async def test_should_allow_renaming_to_same_name(self) -> None:
        custom_list = CustomList.create(name="Same Name")
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = custom_list
        mock_repo.update.return_value = custom_list
        use_case = RenameCustomListUseCase(custom_list_repository=mock_repo)

        result = await use_case.execute(
            RenameCustomListInput(list_id=str(custom_list.id), name="Same Name")
        )

        assert result.name == "Same Name"
        mock_repo.update.assert_called_once()
