"""Tests for RenameCustomListUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    RenameCustomListInput,
)
from src.modules.collections.application.use_cases import RenameCustomListUseCase
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestRenameCustomListUseCase:
    """Tests for renaming custom lists."""

    @pytest.mark.asyncio
    async def test_should_rename_successfully(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Old Name")
        renamed = custom_list.rename("New Name")
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = None
        mock_repo.update.return_value = renamed
        use_case = RenameCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                name="New Name",
            )
        )

        assert isinstance(result, CustomListOutput)
        assert result.name == "New Name"
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = None
        use_case = RenameCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                    name="New Name",
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_name_taken_by_other_list(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="My List")
        other_list = CustomList.create(profile_id=_PROFILE_ID, name="Taken Name")
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = other_list
        use_case = RenameCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id=str(custom_list.id),
                    name="Taken Name",
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_NAME_DUPLICATE"

    @pytest.mark.asyncio
    async def test_should_allow_renaming_to_same_name(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Same Name")
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = custom_list
        mock_repo.update.return_value = custom_list
        use_case = RenameCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                name="Same Name",
            )
        )

        assert result.name == "Same Name"
        mock_repo.update.assert_called_once()
