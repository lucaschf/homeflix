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
