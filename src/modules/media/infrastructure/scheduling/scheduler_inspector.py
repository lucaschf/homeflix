"""Adapter exposing the live ``LibraryScanScheduler`` via the port."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.ports import (
    ScheduledJob,
    SchedulerInspectorPort,
    SchedulerSnapshot,
)

if TYPE_CHECKING:
    from src.infrastructure.scheduling.scheduler_service import LibraryScanScheduler


class LibraryScanSchedulerInspector(SchedulerInspectorPort):
    """Maps the APScheduler-backed scheduler to the read-only port.

    Holds the same ``LibraryScanScheduler`` singleton the lifespan
    starts, so its snapshot reflects the jobs actually registered and
    running. When the scheduler is disabled (never started) the
    snapshot reports ``running=False`` with no jobs.
    """

    def __init__(self, scheduler: LibraryScanScheduler) -> None:
        self._scheduler = scheduler

    def snapshot(self) -> SchedulerSnapshot:
        """Return the current scheduler state."""
        jobs = [
            ScheduledJob(
                job_id=job.id,
                next_run_at=job.next_run_at,
                schedule=job.schedule,
            )
            for job in self._scheduler.list_jobs()
        ]
        return SchedulerSnapshot(running=self._scheduler.is_running, jobs=jobs)


__all__ = ["LibraryScanSchedulerInspector"]
