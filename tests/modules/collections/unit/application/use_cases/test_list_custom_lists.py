"""Tests for ListCustomListsUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.use_cases import ListCustomListsUseCase
from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.repositories import CustomListRepository


@pytest.mark.unit
class TestListCustomListsUseCase:
    """Tests for listing all custom lists."""

    @pytest.mark.asyncio
    async def test_should_return_all_lists(self) -> None:
        lists = [
            CustomList.create(name="Action"),
            CustomList.create(name="Comedy"),
        ]
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.list_all.return_value = lists
        use_case = ListCustomListsUseCase(custom_list_repository=mock_repo)

        result = await use_case.execute()

        assert len(result) == 2
        assert all(isinstance(item, CustomListOutput) for item in result)
        assert result[0].name == "Action"
        assert result[1].name == "Comedy"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_exist(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.list_all.return_value = []
        use_case = ListCustomListsUseCase(custom_list_repository=mock_repo)

        result = await use_case.execute()

        assert result == []
