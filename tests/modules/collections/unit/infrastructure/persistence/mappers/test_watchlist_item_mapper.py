"""Unit tests for WatchlistItemMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.mappers import (
    WatchlistItemMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    WatchlistItemModel,
)
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestWatchlistItemMapper:
    """Tests for WatchlistItemMapper."""

    def test_to_model_should_raise_when_id_is_none(self) -> None:
        item = WatchlistItem(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
        )

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            WatchlistItemMapper.to_model(item)

    def test_to_model_should_convert_entity_correctly(self) -> None:
        list_id = ListId.generate()
        added_at = datetime.now(UTC)
        item = WatchlistItem(
            id=list_id,
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
            added_at=added_at,
        )

        model = WatchlistItemMapper.to_model(item)

        assert model.external_id == str(list_id)
        assert model.profile_id == _PROFILE_ID.value
        assert model.media_id == "mov_abc123def456"
        assert model.media_type == MediaType.MOVIE
        assert model.added_at == added_at

    def test_to_entity_should_convert_model_correctly(self) -> None:
        list_id = ListId.generate()
        added_at = datetime.now(UTC)
        now = datetime.now(UTC)
        model = WatchlistItemModel(
            external_id=str(list_id),
            profile_id=_PROFILE_ID.value,
            media_id="ser_xyz789abc123",
            media_type="series",
            added_at=added_at,
        )
        model.created_at = now
        model.updated_at = now

        entity = WatchlistItemMapper.to_entity(model)

        assert entity.id == list_id
        assert entity.profile_id == _PROFILE_ID
        assert entity.media_id.value == "ser_xyz789abc123"
        assert entity.media_type == MediaType.SERIES
        assert entity.added_at == added_at

    def test_round_trip_should_preserve_fields(self) -> None:
        list_id = ListId.generate()
        added_at = datetime.now(UTC)
        original = WatchlistItem(
            id=list_id,
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
            added_at=added_at,
        )
        model = WatchlistItemMapper.to_model(original)
        model.created_at = original.created_at
        model.updated_at = original.updated_at

        result = WatchlistItemMapper.to_entity(model)

        assert result.id == original.id
        assert result.profile_id == original.profile_id
        assert result.media_id == original.media_id
        assert result.media_type == original.media_type
        assert result.added_at == original.added_at

    def test_update_model_refreshes_added_at_only(self) -> None:
        # update_model is only called from the soft-delete restore
        # path, where the caller has already located ``model`` by
        # the (profile_id, media_id) composite key. Refreshing the
        # added_at is the only mutation that makes sense — leaving
        # the identity-shaping fields intact prevents accidental
        # unique-constraint violations.
        list_id = ListId.generate()
        old_added_at = datetime(2024, 1, 1, tzinfo=UTC)
        new_added_at = datetime(2025, 6, 1, tzinfo=UTC)
        model = WatchlistItemModel(
            external_id=str(list_id),
            profile_id=_PROFILE_ID.value,
            media_id="mov_old000000000",
            media_type="movie",
            added_at=old_added_at,
        )
        same_key_entity = WatchlistItem(
            id=list_id,
            profile_id=_PROFILE_ID,
            media_id="mov_old000000000",
            media_type=MediaType.MOVIE,
            added_at=new_added_at,
        )

        result = WatchlistItemMapper.update_model(model, same_key_entity)

        assert result.added_at == new_added_at
        assert result.media_id == "mov_old000000000"
        assert result.media_type == "movie"

    def test_update_model_does_not_overwrite_identity_fields(self) -> None:
        # If a caller (incorrectly) hands an entity whose
        # ``media_id`` or ``media_type`` differs from the model's,
        # the mapper must not propagate the change — those fields
        # are part of the composite uniqueness contract.
        list_id = ListId.generate()
        model = WatchlistItemModel(
            external_id=str(list_id),
            profile_id=_PROFILE_ID.value,
            media_id="mov_old000000000",
            media_type="movie",
            added_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        mismatched_entity = WatchlistItem(
            id=list_id,
            profile_id=_PROFILE_ID,
            media_id="ser_new000000000",
            media_type=MediaType.SERIES,
            added_at=datetime(2025, 6, 1, tzinfo=UTC),
        )

        result = WatchlistItemMapper.update_model(model, mismatched_entity)

        assert result.media_id == "mov_old000000000"
        assert result.media_type == "movie"
