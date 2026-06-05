"""Tests for the watch_progress OnMovieMergedHandler (ADR-015 Phase 2)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.domain.events import (
    MediaCreatedEvent,
    MovieMergedEvent,
)
from src.modules.watch_progress.application.event_handlers.on_movie_merged import (
    OnMovieMergedHandler,
)
from src.shared_kernel.value_objects.media_id import MovieId


def _uow_mock() -> tuple[MagicMock, AsyncMock]:
    """Return (factory, progress_repo) for a single-UoW invocation."""
    progress = AsyncMock()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.progress = progress
    factory = MagicMock(return_value=uow)
    return factory, progress


class TestOnMovieMergedHandlerWatchProgress:
    @pytest.mark.asyncio
    async def test_deletes_loser_progress_rows(self) -> None:
        factory, progress = _uow_mock()
        progress.delete_all_for_movie.return_value = 3
        handler = OnMovieMergedHandler(uow_factory=factory)

        await handler.handle(
            MovieMergedEvent(
                conflict_id="cnf_xxxxxxxxxxxx",
                winner_id=MovieId("mov_winneraaaaaa"),
                loser_id=MovieId("mov_loserbbbbbbb"),
            ),
        )

        progress.delete_all_for_movie.assert_awaited_once_with("mov_loserbbbbbbb")

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self) -> None:
        factory, progress = _uow_mock()
        handler = OnMovieMergedHandler(uow_factory=factory)

        await handler.handle(
            MediaCreatedEvent(media_id=MovieId("mov_abcdefghijkl"), media_type="movie"),
        )

        factory.assert_not_called()
        progress.delete_all_for_movie.assert_not_called()
