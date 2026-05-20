"""Tests for the ``Notification`` aggregate."""

from datetime import UTC, datetime

import pytest

from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import (
    NotificationId,
    NotificationKind,
)


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
