"""Tests for ``OnMediaEnrichedHandler``."""

import logging
from unittest.mock import AsyncMock

import pytest

from src.modules.catalog_requests.application.event_handlers import (
    OnMediaEnrichedHandler,
)
from src.modules.catalog_requests.application.event_handlers.on_media_enriched import (
    _MEDIA_TYPE_TO_REQUESTED,
)
from src.modules.catalog_requests.application.ports import (
    CatalogArrivalNotification,
    NotificationPublisherPort,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from src.modules.media.domain.events import MediaCreatedEvent, MediaEnrichedEvent
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.media_type import MediaType
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
                media_id=MovieId("mov_abcabcabcabc"),
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
                media_id=MovieId("mov_abcabcabcabc"),
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
                media_id=MovieId("mov_abcabcabcabc"),
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
            media_type=RequestedMediaType.SERIES,
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
            RequestedMediaType.SERIES,
        )
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_publishes_notification_when_user_opted_in(self) -> None:
        """When the requester opted in and we know who they are, the
        handler dispatches a ``CatalogArrivalNotification`` to the
        publisher port after committing the fulfillment."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        publisher.publish_catalog_arrival.assert_awaited_once()
        payload = publisher.publish_catalog_arrival.await_args.args[0]
        assert isinstance(payload, CatalogArrivalNotification)
        assert payload.recipient_user_id == "usr_alice"
        assert payload.title == "Alien"
        assert payload.tmdb_id == 348
        assert payload.media_id == "mov_abcabcabcabc"
        assert payload.media_type == "movie"

    @pytest.mark.asyncio
    async def test_no_notification_when_user_did_not_opt_in(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_alice",
            notify_on_arrival=False,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        publisher.publish_catalog_arrival.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_notification_when_requester_anonymous(self) -> None:
        """Legacy rows without a ``requester_user_id`` skip the ping
        even when ``notify_on_arrival=True`` (we have no inbox to
        target)."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        publisher.publish_catalog_arrival.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_notification_without_publisher(self) -> None:
        """The handler stays usable without the Notifications BC
        wired in — fulfillment still happens, publisher path stays
        a no-op."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        handler = OnMediaEnrichedHandler(uow_factory=mocks.factory)

        # No publisher injected: should not raise, fulfillment still happens.
        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_publisher_failure_swallowed(self) -> None:
        """A publisher exception must not leak out — it would
        otherwise propagate into the event bus and short-circuit
        other subscribers of the same event."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        publisher = AsyncMock(spec=NotificationPublisherPort)
        publisher.publish_catalog_arrival.side_effect = RuntimeError("boom")
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        # No exception bubbled up; fulfillment still committed.
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_title_falls_back_to_tmdb_id(self) -> None:
        """Legacy rows without a title snapshot still produce a
        readable notification by falling back to ``tmdb/<type>/<id>``."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        publisher = AsyncMock(spec=NotificationPublisherPort)
        handler = OnMediaEnrichedHandler(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        await handler.handle(
            MediaEnrichedEvent(
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
                tmdb_id=348,
            ),
        )

        payload = publisher.publish_catalog_arrival.await_args.args[0]
        assert payload.title == "tmdb/movie/348"


@pytest.mark.unit
class TestMediaTypeAclMapping:
    """The cross-BC ACL map must stay total over the canonical MediaType."""

    def test_map_covers_every_media_type_member(self) -> None:
        # If a MediaType member is added without a RequestedMediaType
        # mapping, arrival events for it would be dropped (logged at
        # ERROR) and the request never fulfilled. Fail here instead.
        assert set(_MEDIA_TYPE_TO_REQUESTED) == set(MediaType)

    def test_each_mapping_value_is_a_requested_media_type(self) -> None:
        for mapped in _MEDIA_TYPE_TO_REQUESTED.values():
            assert isinstance(mapped, RequestedMediaType)
