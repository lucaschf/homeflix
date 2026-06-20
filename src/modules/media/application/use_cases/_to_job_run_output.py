"""Internal helper projecting a ``JobRun`` aggregate into the API DTO."""

from src.modules.media.application.dtos.job_dtos import JobRunOutput
from src.modules.media.domain.entities.job_run import JobRun


def job_run_to_output(run: JobRun) -> JobRunOutput:
    """Convert a ``JobRun`` to ``JobRunOutput`` (timestamps as ISO-8601)."""
    if run.id is None:
        raise ValueError("Cannot project an unpersisted JobRun to output")
    return JobRunOutput(
        id=str(run.id),
        job_id=run.job_id,
        status=run.status.value,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        duration_ms=run.duration_ms,
        error=run.error,
    )


__all__ = ["job_run_to_output"]
