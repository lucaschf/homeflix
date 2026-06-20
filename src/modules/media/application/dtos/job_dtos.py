"""DTOs for the admin Jobs dashboard."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobRunOutput:
    """API-facing shape of a single recorded job execution."""

    id: str
    job_id: str
    status: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    error: str | None


@dataclass(frozen=True)
class JobOutput:
    """One job on the dashboard: live schedule + its last execution.

    Attributes:
        job_id: Stable scheduler job id.
        scheduled: Whether the job is currently registered with a
            running scheduler (``False`` for a disabled job that only
            shows up because it has history).
        schedule: Human-readable trigger, or ``None`` when not scheduled.
        next_run_at: ISO-8601 of the next fire, or ``None``.
        running: Whether a run is in progress right now.
        last_run: The most recent recorded execution, or ``None``.
    """

    job_id: str
    scheduled: bool
    schedule: str | None
    next_run_at: str | None
    running: bool
    last_run: JobRunOutput | None


@dataclass(frozen=True)
class JobsOverviewOutput:
    """Top-level dashboard payload."""

    scheduler_running: bool
    jobs: list[JobOutput]


@dataclass(frozen=True)
class ListJobRunsInput:
    """Input for ``ListJobRunsUseCase``."""

    job_id: str | None = None
    limit: int = 50
    offset: int = 0


__all__ = [
    "JobOutput",
    "JobRunOutput",
    "JobsOverviewOutput",
    "ListJobRunsInput",
]
