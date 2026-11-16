"""Tests for the collections OnMovieCompletedHandler."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from structlog.testing import capture_logs

from src.modules.collections.application.event_handlers.on_movie_completed import (
    OnMovieCompletedHandler,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.integration_events import MovieCompletedEvent, MovieMergedEvent
from src.shared_kernel.value_objects.media_id import MovieId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_MOVIE_ID = MovieId("mov_abc123def456")


def _uow_mock() -> tuple[MagicMock, AsyncMock, AsyncMock]:
    """Return (factory, watchlist_repo, custom_lists_repo)."""
    watchlist = AsyncMock()
    custom_lists = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.watchlist = watchlist
    uow.custom_lists = custom_lists
    factory = MagicMock(return_value=uow)
    return factory, watchlist, custom_lists


class TestOnMovieCompletedHandler:
    """A finished movie leaves that profile's watchlist, and only that."""

    @pytest.mark.asyncio
    async def test_removes_the_movie_from_the_profiles_watchlist(self) -> None:
        factory, watchlist, _ = _uow_mock()
        watchlist.remove.return_value = True

        await OnMovieCompletedHandler(uow_factory=factory).handle(
            MovieCompletedEvent(profile_id=_PROFILE_ID, movie_id=_MOVIE_ID),
        )

        watchlist.remove.assert_awaited_once_with(CollectionMediaId(_MOVIE_ID.value), _PROFILE_ID)

    @pytest.mark.asyncio
    async def test_a_movie_off_the_watchlist_is_a_no_op(self) -> None:
        factory, watchlist, _ = _uow_mock()
        watchlist.remove.return_value = False

        await OnMovieCompletedHandler(uow_factory=factory).handle(
            MovieCompletedEvent(profile_id=_PROFILE_ID, movie_id=_MOVIE_ID),
        )

        watchlist.remove.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_leaves_custom_lists_alone(self) -> None:
        """Custom lists are curated by hand; finishing a movie keeps it there."""
        factory, _, custom_lists = _uow_mock()

        await OnMovieCompletedHandler(uow_factory=factory).handle(
            MovieCompletedEvent(profile_id=_PROFILE_ID, movie_id=_MOVIE_ID),
        )

        assert custom_lists.mock_calls == []

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self) -> None:
        factory, watchlist, _ = _uow_mock()

        await OnMovieCompletedHandler(uow_factory=factory).handle(
            MovieMergedEvent(
                conflict_id="cnf_xxxxxxxxxxxx",
                winner_id=MovieId("mov_winneraaaaaa"),
                loser_id=MovieId("mov_loserbbbbbbb"),
            ),
        )

        factory.assert_not_called()
        watchlist.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_the_removal_as_a_structured_event(self) -> None:
        factory, watchlist, _ = _uow_mock()
        watchlist.remove.return_value = True

        with capture_logs() as logs:
            await OnMovieCompletedHandler(uow_factory=factory).handle(
                MovieCompletedEvent(profile_id=_PROFILE_ID, movie_id=_MOVIE_ID),
            )

        assert logs == [
            {
                "event": "Finished movie removed from watchlist",
                "log_level": "info",
                "handler": "OnMovieCompletedHandler",
                "movie_id": _MOVIE_ID.value,
                "profile_id": _PROFILE_ID.value,
            }
        ]
