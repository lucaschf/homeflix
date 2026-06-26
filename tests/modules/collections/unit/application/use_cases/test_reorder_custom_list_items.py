"""Tests for ReorderCustomListItemsUseCase."""

import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import ReorderCustomListItemsInput
from src.modules.collections.application.use_cases import ReorderCustomListItemsUseCase
from src.modules.collections.domain.entities import CustomList
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestReorderCustomListItemsUseCase:
    """Tests for persisting a manual item order."""

    @pytest.mark.asyncio
    async def test_should_reorder_with_typed_ids(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        use_case = ReorderCustomListItemsUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            ReorderCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                media_ids=("mov_abc123def456", "ser_xyz789abc123"),
            )
        )

        mock_repo.reorder_items.assert_called_once_with(
            str(custom_list.id),
            [CollectionMediaId("mov_abc123def456"), CollectionMediaId("ser_xyz789abc123")],
            _PROFILE_ID,
        )

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        use_case = ReorderCustomListItemsUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                ReorderCustomListItemsInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                    media_ids=("mov_abc123def456",),
                )
            )

        assert exc_info.value.resource_type == "CustomList"
        mocks.custom_lists.reorder_items.assert_not_called()
