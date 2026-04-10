"""Tests for WatchlistItem aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects import CollectionMediaType


@pytest.mark.unit
class TestWatchlistItemCreation:
    """Tests for WatchlistItem instantiation."""

    def test_should_create_with_required_fields(self) -> None:
        item = WatchlistItem(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.id is None
        assert item.media_id == "mov_abc123def456"
        assert item.media_type == CollectionMediaType.MOVIE

    def test_should_create_via_factory_with_auto_id(self) -> None:
        item = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.id is not None
        assert isinstance(item.id, ListId)
        assert item.id.prefix == "lst"

    def test_should_create_with_series_media_type(self) -> None:
        item = WatchlistItem.create(
            media_id="ser_abc123def456",
            media_type=CollectionMediaType.SERIES,
        )

        assert item.media_type == CollectionMediaType.SERIES

    def test_should_have_added_at_timestamp(self) -> None:
        item = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item.added_at is not None


@pytest.mark.unit
class TestWatchlistItemImmutability:
    """Tests for WatchlistItem frozen behavior."""

    def test_should_be_frozen(self) -> None:
        item = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        with pytest.raises(DomainValidationException):
            item.media_id = "mov_other1234567"  # type: ignore[misc]

    def test_should_not_allow_media_type_change(self) -> None:
        item = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        with pytest.raises(DomainValidationException):
            item.media_type = CollectionMediaType.SERIES  # type: ignore[misc]


@pytest.mark.unit
class TestWatchlistItemEquality:
    """Tests for WatchlistItem equality and hashing."""

    def test_should_be_equal_by_id(self) -> None:
        list_id = ListId.generate()
        item_a = WatchlistItem(
            id=list_id,
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )
        item_b = WatchlistItem(
            id=list_id,
            media_id="ser_xyz789abc123",
            media_type=CollectionMediaType.SERIES,
        )

        assert item_a == item_b

    def test_should_not_be_equal_with_different_ids(self) -> None:
        item_a = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )
        item_b = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert item_a != item_b

    def test_should_be_hashable(self) -> None:
        item = WatchlistItem.create(
            media_id="mov_abc123def456",
            media_type=CollectionMediaType.MOVIE,
        )

        assert hash(item) is not None
        assert {item}
