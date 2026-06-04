"""Tests for RemoveItemFromCustomListUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RemoveItemFromCustomListInput
from src.modules.collections.application.use_cases import (
    RemoveItemFromCustomListUseCase,
)
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestRemoveItemFromCustomListUseCase:
    """Tests for removing items from custom lists."""

    @pytest.mark.asyncio
    async def test_should_remove_item_successfully(self) -> None:
        custom_list = CustomList.create(
            profile_id=_PROFILE_ID, name="Test", existing_count=0
        ).with_updates(item_count=3)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = True
        mock_repo.update.return_value = custom_list.decrement_item_count()
        use_case = RemoveItemFromCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            RemoveItemFromCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
            )
        )

        mock_repo.remove_item.assert_called_once_with(
            str(custom_list.id), "mov_abc123def456", _PROFILE_ID
        )
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = None
        use_case = RemoveItemFromCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveItemFromCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                    media_id="mov_abc123def456",
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_item_not_in_list(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = False
        use_case = RemoveItemFromCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RemoveItemFromCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id=str(custom_list.id),
                    media_id="mov_notinlist0000",
                )
            )

        assert exc_info.value.resource_type == "CustomListItem"

    @pytest.mark.asyncio
    async def test_should_decrement_item_count_after_removal(self) -> None:
        custom_list = CustomList.create(
            profile_id=_PROFILE_ID, name="Test", existing_count=0
        ).with_updates(item_count=5)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.remove_item.return_value = True
        mock_repo.update.return_value = custom_list.decrement_item_count()
        use_case = RemoveItemFromCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            RemoveItemFromCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
            )
        )

        updated_list = mock_repo.update.call_args[0][0]
        assert updated_list.item_count == 4
