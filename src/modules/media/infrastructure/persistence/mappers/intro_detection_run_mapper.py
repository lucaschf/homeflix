"""Mapper between IntroDetectionRun aggregate and its ORM model."""

from src.modules.media.domain.entities.intro_detection_run import (
    EpisodeDetectionResult,
    IntroDetectionRun,
)
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId
from src.modules.media.domain.value_objects.intro_detection_state import IntroDetectionState
from src.modules.media.infrastructure.persistence.models.intro_detection_run import (
    IntroDetectionRunModel,
)


class IntroDetectionRunMapper:
    """Translate IntroDetectionRun ↔ IntroDetectionRunModel."""

    @staticmethod
    def to_entity(model: IntroDetectionRunModel) -> IntroDetectionRun:
        """Hydrate the aggregate from a persisted row."""
        return IntroDetectionRun(
            id=IntroDetectionRunId(model.external_id),
            series_id=model.series_id,
            series_title=model.series_title,
            season_id=model.season_id,
            season_number=model.season_number,
            algorithm=model.algorithm,
            outcome=IntroDetectionState(model.outcome),
            ref_count=model.ref_count,
            analyzed_count=model.analyzed_count,
            detected_count=model.detected_count,
            persisted_count=model.persisted_count,
            min_confidence=model.min_confidence,
            episode_results=[
                EpisodeDetectionResult(
                    episode_id=str(item["episode_id"]),
                    episode_number=int(item["episode_number"]),
                    start_seconds=float(item["start_seconds"]),
                    end_seconds=float(item["end_seconds"]),
                    confidence=float(item["confidence"]),
                    persisted=bool(item["persisted"]),
                )
                for item in (model.episode_results or [])
            ],
            error=model.error,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: IntroDetectionRun) -> IntroDetectionRunModel:
        """Build a fresh model from a brand-new aggregate."""
        if entity.id is None:
            raise ValueError("IntroDetectionRun must have an id before mapping to model")
        return IntroDetectionRunModel(
            external_id=str(entity.id),
            series_id=entity.series_id,
            series_title=entity.series_title,
            season_id=entity.season_id,
            season_number=entity.season_number,
            algorithm=entity.algorithm,
            outcome=entity.outcome.value,
            ref_count=entity.ref_count,
            analyzed_count=entity.analyzed_count,
            detected_count=entity.detected_count,
            persisted_count=entity.persisted_count,
            min_confidence=entity.min_confidence,
            episode_results=[result.model_dump() for result in entity.episode_results],
            error=entity.error,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
        )


__all__ = ["IntroDetectionRunMapper"]
