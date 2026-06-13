"""Tests for ToggleWatchlistUseCase."""


import pytest
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import (
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
)
from src.modules.collections.application.use_cases import ToggleWatchlistUseCase
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestToggleWatchlistUseCase:
    """Tests for toggling watchlist items."""

    @pytest.mark.asyncio
    async def test_should_add_when_not_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = False
        mock_repo.add.return_value = WatchlistItem.create(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
        )
        use_case = ToggleWatchlistUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        assert isinstance(result, ToggleWatchlistOutput)
        assert result.media_id == "mov_abc123def456"
        assert result.added is True
        mock_repo.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_remove_when_already_in_watchlist(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = True
        mock_repo.remove.return_value = True
        use_case = ToggleWatchlistUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        assert result.added is False
        assert result.media_id == "mov_abc123def456"
        mock_repo.remove.assert_called_once_with(CollectionMediaId("mov_abc123def456"), _PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_toggle_series(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.watchlist
        mock_repo.exists.return_value = False
        mock_repo.add.return_value = WatchlistItem.create(
            profile_id=_PROFILE_ID,
            media_id="ser_abc123def456",
            media_type=MediaType.SERIES,
        )
        use_case = ToggleWatchlistUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ToggleWatchlistInput(
                profile_id=_PROFILE_ID.value,
                media_id="ser_abc123def456",
                media_type=MediaType.SERIES,
            )
        )

        assert result.added is True
