"""Unit tests for MediaConflictMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.media.infrastructure.persistence.mappers.media_conflict_mapper import (
    MediaConflictMapper,
)
from src.modules.media.infrastructure.persistence.models.media_conflict import (
    MediaConflictModel,
)
from src.shared_kernel.value_objects.media_type import MediaType

_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def _model(
    *, candidate_a_type: str = "movie", candidate_b_type: str = "movie"
) -> MediaConflictModel:
    model = MediaConflictModel(
        external_id="cnf_aaaaaaaaaaaa",
        candidate_a_id="mov_aaaaaaaaaaaa",
        candidate_a_type=candidate_a_type,
        candidate_b_id="mov_bbbbbbbbbbbb",
        candidate_b_type=candidate_b_type,
        match_reason="tmdb_id",
        runtime_delta_minutes=0.0,
        suggested_action="likely_same_release",
        resolved_at=None,
        resolution=None,
        winner_id=None,
        resolution_source=None,
    )
    model.created_at = _NOW
    model.updated_at = _NOW
    return model


class TestMediaConflictMapperToEntity:
    """``to_entity`` hydrates the aggregate from a row."""

    def test_candidate_types_become_media_type_enum(self) -> None:
        entity = MediaConflictMapper.to_entity(_model())

        assert entity.candidate_a.type is MediaType.MOVIE
        assert entity.candidate_b.type is MediaType.MOVIE

    def test_unknown_candidate_type_fails_loudly(self) -> None:
        # ADR-016: a corrupted persisted discriminator must surface as an
        # observable error at the boundary, not round-trip silently and
        # leave the conflict permanently unresolvable downstream.
        with pytest.raises(ValueError):
            MediaConflictMapper.to_entity(_model(candidate_a_type="movies"))


class TestMediaConflictMapperRoundTrip:
    """Entity → model → entity preserves the typed discriminator."""

    def test_round_trip_preserves_candidate_types(self) -> None:
        entity = MediaConflictMapper.to_entity(_model())
        model = MediaConflictMapper.to_model(entity)

        # to_model writes the raw enum value back to the String column...
        assert model.candidate_a_type == "movie"
        assert model.candidate_b_type == "movie"

        # ...and reading it back yields the typed enum again.
        model.created_at = _NOW
        model.updated_at = _NOW
        rehydrated = MediaConflictMapper.to_entity(model)
        assert rehydrated.candidate_a.type is MediaType.MOVIE
        assert rehydrated.candidate_b.type is MediaType.MOVIE
