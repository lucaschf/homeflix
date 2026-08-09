"""Tests for RevokeCustomListShareUseCase."""

import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import RevokeCustomListShareInput
from src.modules.collections.application.use_cases import RevokeCustomListShareUseCase
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestRevokeCustomListShareUseCase:
    """Revoking a share clears the token and drops followers."""

    @pytest.mark.asyncio
    async def test_revoke_clears_token_and_drops_followers(self) -> None:
        shared = CustomList.create(profile_id=_PROFILE_ID, name="Mine", existing_count=0).shared()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = shared
        mocks.list_follows.remove_all_for_list.return_value = 3
        use_case = RevokeCustomListShareUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            RevokeCustomListShareInput(profile_id=_PROFILE_ID.value, list_id=str(shared.id))
        )

        # Token cleared via update, and every follow removed (edge case 2).
        mocks.custom_lists.update.assert_awaited_once()
        updated = mocks.custom_lists.update.await_args.args[0]
        assert updated.share_token is None
        mocks.list_follows.remove_all_for_list.assert_awaited_once_with(shared.id)

    @pytest.mark.asyncio
    async def test_raises_when_not_owner(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        use_case = RevokeCustomListShareUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RevokeCustomListShareInput(profile_id=_PROFILE_ID.value, list_id="lst_notmine00001")
            )
