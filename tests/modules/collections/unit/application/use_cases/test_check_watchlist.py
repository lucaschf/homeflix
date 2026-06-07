"""Tests for CheckWatchlistUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import CheckWatchlistInput
from src.modules.collections.application.use_cases import CheckWatchlistUseCase
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestCheckWatchlistUseCase:
    """Tests for checking if a media is in the watchlist."""

    @pytest.mark.asyncio
    async def test_should_return_true_when_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = True
        use_case = CheckWatchlistUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CheckWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is True
        mocks.watchlist.exists.assert_called_once_with(
            CollectionMediaId("mov_abc123def456"), _PROFILE_ID
        )

    @pytest.mark.asyncio
    async def test_should_return_false_when_not_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.exists.return_value = False
        use_case = CheckWatchlistUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CheckWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is False
