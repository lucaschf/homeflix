"""Tests for UnfollowCustomListUseCase."""

import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import UnfollowCustomListInput
from src.modules.collections.application.use_cases import UnfollowCustomListUseCase
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects.profile_id import ProfileId

_FOLLOWER = ProfileId("prf_follower0001")
_LIST_ID = ListId("lst_abc123def456")


@pytest.mark.unit
class TestUnfollowCustomListUseCase:
    """Unfollowing a list."""

    @pytest.mark.asyncio
    async def test_removes_follow(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.list_follows.remove.return_value = True
        use_case = UnfollowCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            UnfollowCustomListInput(profile_id=_FOLLOWER.value, list_id=_LIST_ID.value)
        )

        mocks.list_follows.remove.assert_awaited_once_with(_FOLLOWER, _LIST_ID)

    @pytest.mark.asyncio
    async def test_idempotent_when_not_following(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.list_follows.remove.return_value = False
        use_case = UnfollowCustomListUseCase(uow_factory=mocks.factory)

        # Must not raise.
        await use_case.execute(
            UnfollowCustomListInput(profile_id=_FOLLOWER.value, list_id=_LIST_ID.value)
        )

    @pytest.mark.asyncio
    async def test_malformed_list_id_is_noop(self) -> None:
        mocks = make_collections_uow_mock()
        use_case = UnfollowCustomListUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            UnfollowCustomListInput(profile_id=_FOLLOWER.value, list_id="not-an-id")
        )

        mocks.list_follows.remove.assert_not_awaited()
