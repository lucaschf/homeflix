"""Tests for ListCustomListsUseCase."""


import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_profile_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import CustomListOutput
from src.modules.collections.application.use_cases import ListCustomListsUseCase
from src.modules.collections.application.use_cases.list_custom_lists import (
    ListCustomListsInput,
)
from src.modules.collections.domain.entities import CustomList, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_OWNER_ID = ProfileId("prf_owner0000001")


@pytest.mark.unit
class TestListCustomListsUseCase:
    """Tests for listing owned + followed custom lists."""

    @pytest.mark.asyncio
    async def test_should_return_all_owned_lists(self) -> None:
        lists = [
            CustomList.create(profile_id=_PROFILE_ID, name="Action", existing_count=0),
            CustomList.create(profile_id=_PROFILE_ID, name="Comedy", existing_count=0),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = lists
        mocks.list_follows.list_for_follower.return_value = []
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        assert all(isinstance(item, CustomListOutput) for item in result)
        assert result[0].name == "Action"
        assert result[1].name == "Comedy"
        assert all(not item.is_followed for item in result)
        mocks.custom_lists.list_all.assert_called_once_with(_PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_exist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = []
        mocks.list_follows.list_for_follower.return_value = []
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_append_followed_lists_flagged_with_owner_name(self) -> None:
        owned = CustomList.create(profile_id=_PROFILE_ID, name="Mine", existing_count=0)
        followed = CustomList.create(
            profile_id=_OWNER_ID, name="Lucas' picks", existing_count=0
        ).shared()
        follow = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId(str(followed.id)),
        )
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = [owned]
        mocks.list_follows.list_for_follower.return_value = [follow]
        mocks.custom_lists.find_by_id_unscoped.return_value = followed
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock({_OWNER_ID.value: "Lucas"}),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        # Owned row first, followed row second.
        assert result[0].is_followed is False
        assert result[1].is_followed is True
        assert result[1].owner_name == "Lucas"
        assert result[1].name == "Lucas' picks"

    @pytest.mark.asyncio
    async def test_should_drop_followed_list_that_is_gone_or_unshared(self) -> None:
        follow_gone = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId("lst_gone00000001"),
        )
        follow_unshared = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId("lst_unshared0001"),
        )
        unshared_list = CustomList.create(
            profile_id=_OWNER_ID, name="No longer shared", existing_count=0
        )
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = []
        mocks.list_follows.list_for_follower.return_value = [follow_gone, follow_unshared]
        mocks.custom_lists.find_by_id_unscoped.side_effect = [None, unshared_list]
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert result == []
