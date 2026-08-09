"""Tests for FollowSharedListUseCase."""

import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import DomainConflictException
from src.modules.collections.application.dtos import FollowSharedListInput
from src.modules.collections.application.use_cases import FollowSharedListUseCase
from src.modules.collections.domain.entities import CustomList, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects.profile_id import ProfileId

_OWNER = ProfileId("prf_owner0000001")
_FOLLOWER = ProfileId("prf_follower0001")


def _shared_list() -> CustomList:
    return CustomList.create(profile_id=_OWNER, name="Owner list", existing_count=0).shared()


@pytest.mark.unit
class TestFollowSharedListUseCase:
    """Following a shared list by token."""

    @pytest.mark.asyncio
    async def test_creates_follow_for_new_follower(self) -> None:
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.list_follows.find.return_value = None
        use_case = FollowSharedListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            FollowSharedListInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        mocks.list_follows.add.assert_awaited_once()
        added = mocks.list_follows.add.await_args.args[0]
        assert added.follower_profile_id == _FOLLOWER
        assert added.list_id == shared.id

    @pytest.mark.asyncio
    async def test_double_follow_is_noop(self) -> None:
        shared = _shared_list()
        existing = ListFollow.create(follower_profile_id=_FOLLOWER, list_id=ListId(str(shared.id)))
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.list_follows.find.return_value = existing
        use_case = FollowSharedListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            FollowSharedListInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        mocks.list_follows.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_owner_cannot_follow_own_list(self) -> None:
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        use_case = FollowSharedListUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainConflictException):
            await use_case.execute(
                FollowSharedListInput(profile_id=_OWNER.value, token=shared.share_token.value)
            )
        mocks.list_follows.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_token_raises_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = None
        use_case = FollowSharedListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                FollowSharedListInput(profile_id=_FOLLOWER.value, token="x" * 24)
            )

    @pytest.mark.asyncio
    async def test_malformed_token_raises_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        use_case = FollowSharedListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(FollowSharedListInput(profile_id=_FOLLOWER.value, token="short"))
        mocks.custom_lists.find_by_share_token.assert_not_awaited()
