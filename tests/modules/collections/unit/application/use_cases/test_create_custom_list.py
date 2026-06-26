"""Tests for CreateCustomListUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CreateCustomListInput,
    CustomListOutput,
)
from src.modules.collections.application.use_cases import CreateCustomListUseCase
from src.modules.collections.domain.entities import MAX_LISTS, CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestCreateCustomListUseCase:
    """Tests for creating custom lists."""

    @pytest.mark.asyncio
    async def test_should_create_list_successfully(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        saved_list = CustomList.create(
            profile_id=_PROFILE_ID, name="Action Movies", existing_count=0
        )
        mock_repo.add.return_value = saved_list
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCustomListInput(profile_id=_PROFILE_ID.value, name="Action Movies")
        )

        assert isinstance(result, CustomListOutput)
        assert result.name == "Action Movies"
        assert result.item_count == 0
        mock_repo.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_create_with_trimmed_description(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        mock_repo.add.side_effect = lambda entity: entity  # echo what was built
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCustomListInput(
                profile_id=_PROFILE_ID.value,
                name="Horror Marathon",
                description="  The season's scares  ",
            )
        )

        assert result.description == "The season's scares"

    @pytest.mark.asyncio
    async def test_should_store_blank_description_as_none(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        mock_repo.add.side_effect = lambda entity: entity
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCustomListInput(profile_id=_PROFILE_ID.value, name="Plain", description="   ")
        )

        assert result.description is None

    @pytest.mark.asyncio
    async def test_should_raise_when_list_limit_reached(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = MAX_LISTS
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                CreateCustomListInput(profile_id=_PROFILE_ID.value, name="New List")
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_LIMIT_EXCEEDED"
        mock_repo.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_when_name_already_exists(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = 1
        mock_repo.find_by_name.return_value = CustomList.create(
            profile_id=_PROFILE_ID, name="Action Movies", existing_count=0
        )
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                CreateCustomListInput(profile_id=_PROFILE_ID.value, name="Action Movies")
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_NAME_DUPLICATE"
        mock_repo.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_strip_name_before_duplicate_check(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.count.return_value = 0
        mock_repo.find_by_name.return_value = None
        saved_list = CustomList.create(
            profile_id=_PROFILE_ID, name="Action Movies", existing_count=0
        )
        mock_repo.add.return_value = saved_list
        use_case = CreateCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            CreateCustomListInput(profile_id=_PROFILE_ID.value, name="  Action Movies  ")
        )

        mock_repo.find_by_name.assert_called_once_with("Action Movies", _PROFILE_ID)
