"""DTOs for the admin Jobs dashboard."""

from dataclasses import dataclass, field


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
        recent_runs: Status codes of the newest runs, oldest-first, so
            the dashboard can render a left-to-right run-health strip
            (the most recent outcome is the last element).
    """

    job_id: str
    scheduled: bool
    schedule: str | None
    next_run_at: str | None
    running: bool
    last_run: JobRunOutput | None
    recent_runs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JobsOverviewOutput:
    """Top-level dashboard payload.

    Attributes:
        scheduler_running: Whether the scheduler is started and ticking.
        jobs: Every job (live or with history), one row each.
        executions_24h: Total runs started in the last 24 hours.
        failures_24h: Runs that failed or were interrupted in the last
            24 hours.
    """

    scheduler_running: bool
    jobs: list[JobOutput]
    executions_24h: int = 0
    failures_24h: int = 0


@dataclass(frozen=True)
class ListJobRunsInput:
    """Input for ``ListJobRunsUseCase``."""

    job_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class TriggerJobInput:
    """Input for ``TriggerJobUseCase``."""

    job_id: str


__all__ = [
    "JobOutput",
    "JobRunOutput",
    "JobsOverviewOutput",
    "ListJobRunsInput",
    "TriggerJobInput",
]
