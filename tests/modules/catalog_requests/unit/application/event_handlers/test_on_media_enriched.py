"""Tests for ``OnMediaEnrichedHandler``."""

import pytest

from src.modules.catalog_requests.application.event_handlers import (
    OnMediaEnrichedHandler,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from src.modules.media.domain.events import MediaCreatedEvent, MediaEnrichedEvent
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


@pytest.mark.unit
class TestOnMediaEnrichedHandler:
    """Tests for the cross-BC fulfillment handler."""

    @pytest.mark.asyncio
    async def test_marks_matching_request_as_fulfilled(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        captured: dict[str, CatalogRequest] = {}

        async def capture_update(req: CatalogRequest) -> CatalogRequest:
            captured["req"] = req
            return req

        mocks.catalog_requests.update.side_effect = capture_update
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id="mov_abc",
                media_type="movie",
                tmdb_id=348,
            ),
        )

        assert captured["req"].is_fulfilled is True
        assert captured["req"].fulfilled_at is not None
        mocks.catalog_requests.find_by_tmdb_id.assert_awaited_once_with(
            348,
            RequestedMediaType.MOVIE,
        )

    @pytest.mark.asyncio
    async def test_no_op_when_no_request_exists(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id="mov_abc",
                media_type="movie",
                tmdb_id=348,
            ),
        )

        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_when_request_already_fulfilled(self) -> None:
        """Force-refresh re-emits the event; the second tick must not
        re-write the fulfilled row, otherwise watchers triple-fire."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        ).mark_fulfilled()
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id="mov_abc",
                media_type="movie",
                tmdb_id=348,
            ),
        )

        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_other_event_types(self) -> None:
        """Defensive guard — the bus could fan an unrelated event in
        if a subscription gets misconfigured. Drop silently rather
        than crash, since handlers run fire-and-forget."""
        mocks = make_catalog_requests_uow_mock()
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaCreatedEvent(media_id="mov_abc", media_type="movie"),
        )

        mocks.catalog_requests.find_by_tmdb_id.assert_not_called()
        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_unknown_media_type(self) -> None:
        """A garbled event payload (unknown ``media_type``) shouldn't
        explode the bus — log and move on."""
        mocks = make_catalog_requests_uow_mock()
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id="mov_abc",
                media_type="episode",
                tmdb_id=42,
            ),
        )

        mocks.catalog_requests.find_by_tmdb_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_matches_series_event(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=1399,
            media_type=RequestedMediaType.SERIES,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id="ser_xyz",
                media_type="series",
                tmdb_id=1399,
            ),
        )

        mocks.catalog_requests.find_by_tmdb_id.assert_awaited_once_with(
            1399,
            RequestedMediaType.SERIES,
        )
        mocks.catalog_requests.update.assert_called_once()
