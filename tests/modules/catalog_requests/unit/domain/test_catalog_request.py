"""Tests for the ``CatalogRequest`` aggregate."""

from datetime import UTC, datetime

import pytest

from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    RequestedMediaType,
)


@pytest.mark.unit
class TestCatalogRequest:
    """Behavior of the ``CatalogRequest`` aggregate."""

    def test_create_assigns_prefixed_id_and_defaults(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            collection_tmdb_id=8091,
        )

        assert isinstance(request.id, CatalogRequestId)
        assert str(request.id).startswith("req_")
        assert request.tmdb_id == 348
        assert request.collection_tmdb_id == 8091
        assert request.notify_on_arrival is False
        assert request.is_fulfilled is False
        assert request.fulfilled_at is None

    def test_enable_notification_sets_flag(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )

        updated = request.enable_notification()

        assert updated.notify_on_arrival is True
        # Aggregate is immutable per ADR-007.
        assert request.notify_on_arrival is False
        assert updated.id == request.id

    def test_mark_fulfilled_stamps_timestamp(self) -> None:
        fixed = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )

        updated = request.mark_fulfilled(fulfilled_at=fixed)

        assert updated.is_fulfilled is True
        assert updated.fulfilled_at == fixed
        assert request.is_fulfilled is False

    def test_reconcile_backfills_only_unset_fields(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )

        reconciled = request.reconcile(
            title="Alien",
            requester_user_id="usr_aaaaaaaaaaaa",
            notify=True,
        )

        assert reconciled is not None
        assert reconciled.title == "Alien"
        assert reconciled.requester_user_id == "usr_aaaaaaaaaaaa"
        assert reconciled.notify_on_arrival is True

    def test_reconcile_does_not_overwrite_first_owner(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_aaaaaaaaaaaa",
        )

        reconciled = request.reconcile(
            title="Aliens",
            requester_user_id="usr_bbbbbbbbbbbb",
        )

        # First-owner-wins: title and requester are already set, and
        # notify defaults to False, so nothing changes.
        assert reconciled is None

    def test_reconcile_notify_is_one_way(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            notify_on_arrival=True,
        )

        # Already subscribed and nothing to backfill → no-op.
        assert request.reconcile(notify=True) is None

    def test_reconcile_returns_none_when_nothing_changes(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_aaaaaaaaaaaa",
            notify_on_arrival=True,
        )

        assert request.reconcile() is None
