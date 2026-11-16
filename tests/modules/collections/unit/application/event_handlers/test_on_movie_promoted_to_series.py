"""Tests for the collections OnMoviePromotedToSeriesHandler logging."""

import pytest
from structlog.testing import capture_logs
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.event_handlers import OnMoviePromotedToSeriesHandler
from src.shared_kernel.integration_events import MoviePromotedToSeriesEvent
from src.shared_kernel.value_objects.media_id import EpisodeId, MovieId, SeriesId


@pytest.mark.unit
class TestOnMoviePromotedToSeriesHandlerLogging:
    @pytest.mark.asyncio
    async def test_logs_the_repoint_as_a_structured_event(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.rewrite_media_id.return_value = 1
        mocks.custom_lists.rewrite_item_media_id.return_value = 2

        with capture_logs() as logs:
            await OnMoviePromotedToSeriesHandler(uow_factory=mocks.factory).handle(
                MoviePromotedToSeriesEvent(
                    movie_id=MovieId("mov_abc123def456"),
                    series_id=SeriesId("ser_xyz789abc123"),
                    first_episode_id=EpisodeId("epi_abc123def457"),
                )
            )

        assert logs == [
            {
                "event": "Collection entries repointed to promoted series",
                "log_level": "info",
                "handler": "OnMoviePromotedToSeriesHandler",
                "watchlist_updated": 1,
                "lists_updated": 2,
                "movie_id": "mov_abc123def456",
                "series_id": "ser_xyz789abc123",
            }
        ]
