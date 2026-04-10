"""Tests for DeleteCustomListUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.use_cases import DeleteCustomListUseCase
from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.repositories import CustomListRepository


@pytest.mark.unit
class TestDeleteCustomListUseCase:
    """Tests for deleting custom lists."""

    @pytest.mark.asyncio
    async def test_should_delete_successfully(self) -> None:
        custom_list = CustomList.create(name="To Delete")
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.remove.return_value = True
        use_case = DeleteCustomListUseCase(custom_list_repository=mock_repo)

        await use_case.execute(str(custom_list.id))

        mock_repo.remove.assert_called_once_with(str(custom_list.id))

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mock_repo = AsyncMock(spec=CustomListRepository)
        mock_repo.remove.return_value = False
        use_case = DeleteCustomListUseCase(custom_list_repository=mock_repo)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute("lst_nonexistent00")

        assert exc_info.value.resource_type == "CustomList"
