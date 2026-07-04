"""Mapper between SubtitleOcrRun aggregate and its ORM model."""

from src.modules.media.domain.entities.subtitle_ocr_run import (
    SubtitleOcrRun,
    SubtitleTrackOcrResult,
)
from src.modules.media.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
from src.modules.media.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId
from src.modules.media.infrastructure.persistence.models.subtitle_ocr_run import (
    SubtitleOcrRunModel,
)


class SubtitleOcrRunMapper:
    """Translate SubtitleOcrRun ↔ SubtitleOcrRunModel."""

    @staticmethod
    def to_entity(model: SubtitleOcrRunModel) -> SubtitleOcrRun:
        """Hydrate the aggregate from a persisted row."""
        return SubtitleOcrRun(
            id=SubtitleOcrRunId(model.external_id),
            media_kind=model.media_kind,
            media_id=model.media_id,
            media_title=model.media_title,
            file_path=model.file_path,
            outcome=SubtitleOcrOutcome(model.outcome),
            image_track_count=model.image_track_count,
            extracted_count=model.extracted_count,
            track_results=[
                SubtitleTrackOcrResult(
                    track_index=int(item["track_index"]),
                    language=str(item["language"]),
                    outcome=SubtitleTrackOutcome(item["outcome"]),
                    cue_count=int(item["cue_count"]),
                )
                for item in (model.track_results or [])
            ],
            error=model.error,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SubtitleOcrRun) -> SubtitleOcrRunModel:
        """Build a fresh model from a brand-new aggregate."""
        if entity.id is None:
            raise ValueError("SubtitleOcrRun must have an id before mapping to model")
        return SubtitleOcrRunModel(
            external_id=str(entity.id),
            media_kind=entity.media_kind,
            media_id=entity.media_id,
            media_title=entity.media_title,
            file_path=entity.file_path,
            outcome=entity.outcome.value,
            image_track_count=entity.image_track_count,
            extracted_count=entity.extracted_count,
            track_results=[result.model_dump() for result in entity.track_results],
            error=entity.error,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
        )


__all__ = ["SubtitleOcrRunMapper"]
