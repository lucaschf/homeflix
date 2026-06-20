"""Port exposing the live state of the background scheduler."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledJob:
    """A job currently registered with the scheduler.

    Attributes:
        job_id: Stable scheduler job id.
        next_run_at: ISO-8601 timestamp of the next fire, or ``None``
            when the job is paused / has no future run.
        schedule: Human-readable trigger (e.g. ``interval[0:20:00]``
            or a cron expression).
    """

    job_id: str
    next_run_at: str | None
    schedule: str


@dataclass(frozen=True)
class SchedulerSnapshot:
    """Point-in-time view of the scheduler.

    Attributes:
        running: Whether the scheduler is started and ticking.
        jobs: Every currently-registered job.
    """

    running: bool
    jobs: list[ScheduledJob]


class SchedulerInspectorPort(ABC):
    """Read-only window into the live scheduler for the admin dashboard."""

    @abstractmethod
    def snapshot(self) -> SchedulerSnapshot:
        """Return the current scheduler state (in-memory, no I/O)."""
        ...


__all__ = ["ScheduledJob", "SchedulerInspectorPort", "SchedulerSnapshot"]
