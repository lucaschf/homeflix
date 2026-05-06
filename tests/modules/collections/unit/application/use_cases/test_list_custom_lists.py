"""Tests for ListCustomListsUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.use_cases import ListCustomListsUseCase
from src.modules.collections.application.use_cases.list_custom_lists import (
    ListCustomListsInput,
)
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestListCustomListsUseCase:
    """Tests for listing all custom lists."""

    @pytest.mark.asyncio
    async def test_should_return_all_lists(self) -> None:
        lists = [
            CustomList.create(profile_id=_PROFILE_ID, name="Action"),
            CustomList.create(profile_id=_PROFILE_ID, name="Comedy"),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = lists
        use_case = ListCustomListsUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        assert all(isinstance(item, CustomListOutput) for item in result)
        assert result[0].name == "Action"
        assert result[1].name == "Comedy"
        mocks.custom_lists.list_all.assert_called_once_with(_PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_exist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = []
        use_case = ListCustomListsUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert result == []
