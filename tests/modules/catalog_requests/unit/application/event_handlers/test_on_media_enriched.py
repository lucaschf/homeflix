"""Tests for ``OnMediaEnrichedHandler``."""

import logging
from unittest.mock import AsyncMock

import pytest

from src.modules.catalog_requests.application.event_handlers import (
    OnMediaEnrichedHandler,
)
from src.modules.catalog_requests.application.ports import (
    CatalogArrivalNotification,
    NotificationPublisherPort,
)
from src.modules.catalog_requests.domain.entities import (
    CatalogRequest,
    CatalogSubscription,
)
from src.modules.media.domain.events import MediaCreatedEvent
from src.shared_kernel.integration_events import MediaEnrichedEvent
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.media_type import MediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)

_MOVIE_EVENT = MediaEnrichedEvent(
    media_id=MovieId("mov_abcabcabcabc"),
    media_type="movie",
    tmdb_id=348,
)


@pytest.mark.unit
class TestOnMediaEnrichedHandler:
    """Tests for the cross-BC fulfillment handler."""

    @pytest.mark.asyncio
    async def test_marks_matching_request_as_fulfilled(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
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

        await handler.handle(_MOVIE_EVENT)

        assert captured["req"].is_fulfilled is True
        assert captured["req"].fulfilled_at is not None
        mocks.catalog_requests.find_by_tmdb_id.assert_awaited_once_with(
            348,
            MediaType.MOVIE,
        )

    @pytest.mark.asyncio
    async def test_no_op_when_no_request_exists(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(_MOVIE_EVENT)

        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_when_request_already_fulfilled(self) -> None:
        """Force-refresh re-emits the event; the second tick must not
        re-write the fulfilled row, otherwise watchers triple-fire."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        ).mark_fulfilled()
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(_MOVIE_EVENT)

        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_other_event_types(self) -> None:
        """Defensive guard — the bus could fan an unrelated event in
        if a subscription gets misconfigured. Drop silently rather
        than crash, since handlers run fire-and-forget."""
        mocks = make_catalog_requests_uow_mock()
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaCreatedEvent(media_id=MovieId("mov_abcabcabcabc"), media_type="movie"),
        )

        mocks.catalog_requests.find_by_tmdb_id.assert_not_called()
        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_unknown_media_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """An unrecognized ``media_type`` must fail observably (ERROR log)
        and skip — never silently drop, which would leave the matching
        request unfulfilled forever."""
        mocks = make_catalog_requests_uow_mock()
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        with caplog.at_level(logging.ERROR):
            await handler.handle(
                MediaEnrichedEvent(
                    media_id=MovieId("mov_abcabcabcabc"),
                    media_type="episode",
                    tmdb_id=42,
                ),
            )

        mocks.catalog_requests.find_by_tmdb_id.assert_not_called()
        assert any(record.levelno == logging.ERROR for record in caplog.records)

    @pytest.mark.asyncio
    async def test_matches_series_event(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=1399,
            media_type=MediaType.SERIES,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(
            MediaEnrichedEvent(
                media_id=SeriesId("ser_xyzxyzxyzxyz"),
                media_type="series",
                tmdb_id=1399,
            ),
        )

        mocks.catalog_requests.find_by_tmdb_id.assert_awaited_once_with(
            1399,
            MediaType.SERIES,
        )
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_fans_out_to_every_subscriber(self) -> None:
        """One arrival notification per active subscription (ADR-022),
        not just the original requester."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.list_for_request.return_value = [
            CatalogSubscription.create(existing.id, "usr_alice"),
            CatalogSubscription.create(existing.id, "usr_bob"),
        ]
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(_MOVIE_EVENT)

        assert publisher.publish_catalog_arrival.await_count == 2
        recipients = {
            call.args[0].recipient_user_id
            for call in publisher.publish_catalog_arrival.await_args_list
        }
        assert recipients == {"usr_alice", "usr_bob"}
        payload = publisher.publish_catalog_arrival.await_args_list[0].args[0]
        assert isinstance(payload, CatalogArrivalNotification)
        assert payload.title == "Alien"
        assert payload.tmdb_id == 348
        assert payload.media_id == MovieId("mov_abcabcabcabc")
        assert payload.media_type == "movie"

    @pytest.mark.asyncio
    async def test_no_notification_when_no_subscribers(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.list_for_request.return_value = []
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(_MOVIE_EVENT)

        publisher.publish_catalog_arrival.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_notification_without_publisher(self) -> None:
        """The handler stays usable without the Notifications BC wired
        in — fulfillment still happens and the subscriber query is
        skipped entirely."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        await handler.handle(_MOVIE_EVENT)

        mocks.catalog_requests.update.assert_called_once()
        mocks.catalog_subscriptions.list_for_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_subscriber_failure_does_not_block_others(self) -> None:
        """A publish failure for one subscriber is swallowed; the rest
        still get pinged and fulfillment stays committed."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.list_for_request.return_value = [
            CatalogSubscription.create(existing.id, "usr_alice"),
            CatalogSubscription.create(existing.id, "usr_bob"),
        ]
        publisher = AsyncMock(spec=NotificationPublisherPort)
        publisher.publish_catalog_arrival.side_effect = [RuntimeError("boom"), None]
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(_MOVIE_EVENT)

        assert publisher.publish_catalog_arrival.await_count == 2
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_title_falls_back_to_tmdb_id(self) -> None:
        """Legacy rows without a title snapshot still produce a
        readable notification by falling back to ``tmdb/<type>/<id>``."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.list_for_request.return_value = [
            CatalogSubscription.create(existing.id, "usr_alice"),
        ]
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(_MOVIE_EVENT)

        payload = publisher.publish_catalog_arrival.await_args.args[0]
        assert payload.title == "tmdb/movie/348"
