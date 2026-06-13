"""Tests for the collections OnMovieMergedHandler (ADR-015 Phase 2)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.collections.application.event_handlers.on_movie_merged import (
    OnMovieMergedHandler,
)
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.modules.media.domain.events import (
    MediaCreatedEvent,
    MovieMergedEvent,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.media_id import MovieId


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


class TestOnMovieMergedHandlerCollections:
    @pytest.mark.asyncio
    async def test_rewrites_watchlist_and_custom_lists(self) -> None:
        factory, watchlist, custom_lists = _uow_mock()
        watchlist.rewrite_media_id.return_value = 1
        custom_lists.rewrite_item_media_id.return_value = 2
        handler = OnMovieMergedHandler(uow_factory=factory)

        await handler.handle(
            MovieMergedEvent(
                conflict_id="cnf_xxxxxxxxxxxx",
                winner_id=MovieId("mov_winneraaaaaa"),
                loser_id=MovieId("mov_loserbbbbbbb"),
            ),
        )

        watchlist.rewrite_media_id.assert_awaited_once_with(
            from_media_id=CollectionMediaId("mov_loserbbbbbbb"),
            to_media_id=CollectionMediaId("mov_winneraaaaaa"),
            to_media_type=MediaType.MOVIE,
        )
        custom_lists.rewrite_item_media_id.assert_awaited_once_with(
            from_media_id=CollectionMediaId("mov_loserbbbbbbb"),
            to_media_id=CollectionMediaId("mov_winneraaaaaa"),
            to_media_type=MediaType.MOVIE,
        )

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self) -> None:
        factory, watchlist, custom_lists = _uow_mock()
        handler = OnMovieMergedHandler(uow_factory=factory)

        await handler.handle(
            MediaCreatedEvent(media_id=MovieId("mov_abcdefghijkl"), media_type="movie"),
        )

        factory.assert_not_called()
        watchlist.rewrite_media_id.assert_not_called()
        custom_lists.rewrite_item_media_id.assert_not_called()
