"""Tests for ShareCustomListUseCase."""

import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import ShareCustomListInput
from src.modules.collections.application.use_cases import ShareCustomListUseCase
from src.modules.collections.domain.entities import CustomList
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _list() -> CustomList:
    return CustomList.create(profile_id=_PROFILE_ID, name="Mine", existing_count=0)


@pytest.mark.unit
class TestShareCustomListUseCase:
    """Minting and returning share tokens."""

    @pytest.mark.asyncio
    async def test_mints_token_for_unshared_list(self) -> None:
        custom_list = _list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.update.side_effect = lambda cl: cl
        use_case = ShareCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ShareCustomListInput(profile_id=_PROFILE_ID.value, list_id=str(custom_list.id))
        )

        assert result.token
        assert result.url_path == f"/lists/shared/{result.token}"
        mocks.custom_lists.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_existing_token_idempotently(self) -> None:
        already_shared = _list().shared()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = already_shared
        use_case = ShareCustomListUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ShareCustomListInput(profile_id=_PROFILE_ID.value, list_id=str(already_shared.id))
        )

        assert result.token == already_shared.share_token.value
        # No re-persist: the existing token is reused.
        mocks.custom_lists.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_not_owner(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        use_case = ShareCustomListUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ShareCustomListInput(profile_id=_PROFILE_ID.value, list_id="lst_notmine00001")
            )
