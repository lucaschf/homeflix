"""Tests for CreateCustomListUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CreateCustomListInput,
    CustomListOutput,
)
from src.modules.collections.application.use_cases import CreateCustomListUseCase
from src.modules.collections.domain.entities import MAX_LISTS, CustomList
from src.modules.collections.domain.repositories import CustomListRepository


@pytest.mark.unit
class TestCreateCustomListUseCase:
    """Tests for creating custom lists."""

    @pytest.mark.asyncio
    async def test_should_create_list_successfully(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        saved_list = CustomList.create(name="Action Movies")
        mock_repo.add.return_value = saved_list
        use_case = CreateCustomListUseCase(custom_list_repository=mock_repo)

        result = await use_case.execute(CreateCustomListInput(name="Action Movies"))

        assert isinstance(result, CustomListOutput)
        assert result.name == "Action Movies"
        assert result.item_count == 0
        mock_repo.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_limit_reached(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.count.return_value = MAX_LISTS
        use_case = CreateCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(CreateCustomListInput(name="New List"))

        assert exc_info.value.message_code == "CUSTOM_LIST_LIMIT_EXCEEDED"
        mock_repo.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_when_name_already_exists(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.count.return_value = 1
        mock_repo.find_by_name.return_value = CustomList.create(name="Action Movies")
        use_case = CreateCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(CreateCustomListInput(name="Action Movies"))

        assert exc_info.value.message_code == "CUSTOM_LIST_NAME_DUPLICATE"
        mock_repo.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_strip_name_before_duplicate_check(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        saved_list = CustomList.create(name="Action Movies")
        mock_repo.add.return_value = saved_list
        use_case = CreateCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(CreateCustomListInput(name="  Action Movies  "))

        mock_repo.find_by_name.assert_called_once_with("Action Movies")
