"""Tests for the ``CatalogRequest`` aggregate."""

from datetime import UTC, datetime

import pytest

from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import (
    CatalogRequestId,
    CatalogRequestSource,
    CatalogRequestStatus,
)
from src.shared_kernel.value_objects import MediaType


@pytest.mark.unit
class TestCatalogRequest:
    """Behavior of the ``CatalogRequest`` aggregate."""

    def test_create_assigns_prefixed_id_and_defaults(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
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
            media_type=MediaType.MOVIE,
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
            media_type=MediaType.MOVIE,
        )

        updated = request.mark_fulfilled(fulfilled_at=fixed)

        assert updated.is_fulfilled is True
        assert updated.fulfilled_at == fixed
        assert request.is_fulfilled is False

    def test_reconcile_backfills_only_unset_fields(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
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
            media_type=MediaType.MOVIE,
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
            media_type=MediaType.MOVIE,
            notify_on_arrival=True,
        )

        # Already subscribed and nothing to backfill → no-op.
        assert request.reconcile(notify=True) is None

    def test_reconcile_returns_none_when_nothing_changes(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            title="Alien",
            requester_user_id="usr_aaaaaaaaaaaa",
            notify_on_arrival=True,
        )

        assert request.reconcile() is None

    def test_source_is_user_when_a_member_requested(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            requester_user_id="usr_aaaaaaaaaaaa",
        )

        assert request.source is CatalogRequestSource.USER

    def test_source_is_household_without_requester(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        )

        assert request.source is CatalogRequestSource.HOUSEHOLD

    def test_source_is_fixed_at_creation(self) -> None:
        # A later requester backfill (first-owner) records the notify
        # anchor but must not rewrite the household origin.
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        )

        reconciled = request.reconcile(requester_user_id="usr_aaaaaaaaaaaa")

        assert reconciled is not None
        assert reconciled.requester_user_id == "usr_aaaaaaaaaaaa"
        assert reconciled.source is CatalogRequestSource.HOUSEHOLD

    def test_status_tracks_fulfillment(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        )

        assert request.status is CatalogRequestStatus.PENDING
        assert request.mark_fulfilled().status is CatalogRequestStatus.FULFILLED

    def test_create_snapshots_poster(self) -> None:
        request = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            poster_url="https://image.tmdb.org/t/p/original/alien.jpg",
        )

        assert request.poster_url == "https://image.tmdb.org/t/p/original/alien.jpg"

    def test_reconcile_backfills_poster_first_owner_wins(self) -> None:
        without = CatalogRequest.create(tmdb_id=348, media_type=MediaType.MOVIE)
        backfilled = without.reconcile(poster_url="https://img/poster.jpg")
        assert backfilled is not None
        assert backfilled.poster_url == "https://img/poster.jpg"

        # A later poster never overwrites the first snapshot.
        assert backfilled.reconcile(poster_url="https://img/other.jpg") is None
