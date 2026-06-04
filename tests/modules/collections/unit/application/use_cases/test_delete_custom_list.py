"""Tests for DeleteCustomListUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import DeleteCustomListInput
from src.modules.collections.application.use_cases import DeleteCustomListUseCase
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestDeleteCustomListUseCase:
    """Tests for deleting custom lists."""

    @pytest.mark.asyncio
    async def test_should_delete_successfully(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="To Delete", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.remove.return_value = True
        use_case = DeleteCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            DeleteCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        mock_repo.remove.assert_called_once_with(str(custom_list.id), _PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.remove.return_value = False
        use_case = DeleteCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                DeleteCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                )
            )

        assert exc_info.value.resource_type == "CustomList"
