"""Tests for CheckWatchlistUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.collections.application.use_cases import CheckWatchlistUseCase
from src.modules.collections.domain.repositories import WatchlistRepository


@pytest.mark.unit
class TestCheckWatchlistUseCase:
    """Tests for checking if a media is in the watchlist."""

    @pytest.mark.asyncio
    async def test_should_return_true_when_in_watchlist(self) -> None:
        mock_repo = AsyncMock(spec=WatchlistRepository)
        mock_repo.exists.return_value = True
        use_case = CheckWatchlistUseCase(watchlist_repository=mock_repo)

        result = await use_case.execute("mov_abc123def456")

        assert result is True
        mock_repo.exists.assert_called_once_with("mov_abc123def456")

    @pytest.mark.asyncio
    async def test_should_return_false_when_not_in_watchlist(self) -> None:
        mock_repo = AsyncMock(spec=WatchlistRepository)
        mock_repo.exists.return_value = False
        use_case = CheckWatchlistUseCase(watchlist_repository=mock_repo)

        result = await use_case.execute("mov_abc123def456")

        assert result is False
