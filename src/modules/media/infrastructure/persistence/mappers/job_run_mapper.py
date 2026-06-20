"""Translate between :class:`JobRun` aggregates and the ORM row."""

from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.domain.value_objects.job_run_id import JobRunId
from src.modules.media.infrastructure.persistence.models.job_run import JobRunModel


class JobRunMapper:
    """Pure functions converting entity ↔ ``JobRunModel``."""

    @staticmethod
    def to_entity(model: JobRunModel) -> JobRun:
        """Hydrate the aggregate from a row."""
        return JobRun(
            id=JobRunId(model.external_id),
            job_id=model.job_id,
            status=JobRunStatus(model.status),
            started_at=model.started_at,
            finished_at=model.finished_at,
            error=model.error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: JobRun) -> JobRunModel:
        """Build a fresh ``JobRunModel`` from a brand-new aggregate."""
        if entity.id is None:
            raise ValueError("JobRun must have an id before mapping to model")
        return JobRunModel(
            external_id=str(entity.id),
            job_id=entity.job_id,
            status=entity.status.value,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            error=entity.error,
        )

    @staticmethod
    def update_model(model: JobRunModel, entity: JobRun) -> None:
        """Copy mutable fields from the entity onto an existing row."""
        model.job_id = entity.job_id
        model.status = entity.status.value
        model.started_at = entity.started_at
        model.finished_at = entity.finished_at
        model.error = entity.error


__all__ = ["JobRunMapper"]
