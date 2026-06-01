"""Tests for the ``Notification`` aggregate."""

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import (
    NotificationId,
    NotificationKind,
)
from src.shared_kernel.value_objects.media_type import MediaType


@pytest.mark.unit
class TestNotification:
    """Tests for the ``Notification`` domain aggregate."""

    def test_create_generates_id_and_defaults(self) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien chegou ao catálogo",
        )

        assert isinstance(notification.id, NotificationId)
        assert notification.is_read is False
        assert notification.read_at is None
        assert notification.payload == {}
        assert notification.body is None

    def test_create_carries_payload(self) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien",
            payload={"tmdb_id": 348, "media_id": "mov_abc", "media_type": "movie"},
        )

        assert notification.payload["tmdb_id"] == 348
        assert notification.payload["media_id"] == "mov_abc"

    def test_mark_read_stamps_timestamp(self) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien",
        )

        read = notification.mark_read()

        assert read.is_read is True
        assert read.read_at is not None

    def test_mark_read_respects_explicit_timestamp(self) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien",
        )
        fixed = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

        read = notification.mark_read(read_at=fixed)

        assert read.read_at == fixed


@pytest.mark.unit
class TestNotificationPayloadMediaType:
    """The free-form payload's ``media_type`` is validated (ADR-016)."""

    @pytest.mark.parametrize("value", [MediaType.MOVIE, MediaType.SERIES, "movie", "series"])
    def test_accepts_valid_media_type(self, value: object) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien",
            payload={"media_type": value},
        )

        assert notification.payload["media_type"] == value

    def test_rejects_unknown_media_type(self) -> None:
        with pytest.raises(DomainValidationException, match="media_type"):
            Notification.create(
                recipient_user_id="usr_alice",
                kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
                title="Alien",
                payload={"media_type": "film"},
            )

    def test_payload_without_media_type_is_allowed(self) -> None:
        notification = Notification.create(
            recipient_user_id="usr_alice",
            kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
            title="Alien",
            payload={"tmdb_id": 348},
        )

        assert "media_type" not in notification.payload
