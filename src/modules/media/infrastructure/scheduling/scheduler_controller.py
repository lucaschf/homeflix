"""Adapter exposing the live ``LibraryScanScheduler`` control surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.ports import SchedulerControlPort

if TYPE_CHECKING:
    from src.infrastructure.scheduling.scheduler_service import LibraryScanScheduler


class LibraryScanSchedulerController(SchedulerControlPort):
    """Maps the APScheduler-backed scheduler to the control port.

    Holds the same ``LibraryScanScheduler`` singleton the lifespan
    starts, so triggering acts on the jobs actually registered. When the
    scheduler is disabled (never started) no jobs are registered and
    ``trigger`` reports ``False``.
    """

    def __init__(self, scheduler: LibraryScanScheduler) -> None:
        self._scheduler = scheduler

    def trigger(self, job_id: str) -> bool:
        """Reschedule ``job_id`` to run immediately."""
        return self._scheduler.trigger_now(job_id)


__all__ = ["LibraryScanSchedulerController"]
