"""Translate between :class:`MediaConflict` aggregates and ORM rows."""

from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
    SuggestedAction,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.modules.media.infrastructure.persistence.models.media_conflict import (
    MediaConflictModel,
)


class MediaConflictMapper:
    """Pure functions converting ``MediaConflict`` ↔ ``MediaConflictModel``."""

    @staticmethod
    def to_entity(model: MediaConflictModel) -> MediaConflict:
        """Hydrate the aggregate from a row, preserving timestamps."""
        return MediaConflict(
            id=MediaConflictId(model.external_id),
            candidate_a_id=model.candidate_a_id,
            candidate_a_type=model.candidate_a_type,
            candidate_b_id=model.candidate_b_id,
            candidate_b_type=model.candidate_b_type,
            match_reason=MatchReason(model.match_reason),
            runtime_delta_minutes=model.runtime_delta_minutes,
            suggested_action=SuggestedAction(model.suggested_action),
            resolved_at=model.resolved_at,
            resolution=None if model.resolution is None else ResolutionAction(model.resolution),
            winner_id=model.winner_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: MediaConflict) -> MediaConflictModel:
        """Build a fresh ``MediaConflictModel`` from a brand-new aggregate."""
        if entity.id is None:
            raise ValueError("MediaConflict must have an id before mapping to model")
        return MediaConflictModel(
            external_id=str(entity.id),
            candidate_a_id=entity.candidate_a_id,
            candidate_a_type=entity.candidate_a_type,
            candidate_b_id=entity.candidate_b_id,
            candidate_b_type=entity.candidate_b_type,
            match_reason=entity.match_reason.value,
            runtime_delta_minutes=entity.runtime_delta_minutes,
            suggested_action=entity.suggested_action.value,
            resolved_at=entity.resolved_at,
            resolution=None if entity.resolution is None else entity.resolution.value,
            winner_id=entity.winner_id,
        )

    @staticmethod
    def update_model(model: MediaConflictModel, entity: MediaConflict) -> None:
        """Copy mutable fields from the entity onto an existing row."""
        model.candidate_a_id = entity.candidate_a_id
        model.candidate_a_type = entity.candidate_a_type
        model.candidate_b_id = entity.candidate_b_id
        model.candidate_b_type = entity.candidate_b_type
        model.match_reason = entity.match_reason.value
        model.runtime_delta_minutes = entity.runtime_delta_minutes
        model.suggested_action = entity.suggested_action.value
        model.resolved_at = entity.resolved_at
        model.resolution = None if entity.resolution is None else entity.resolution.value
        model.winner_id = entity.winner_id


__all__ = ["MediaConflictMapper"]
