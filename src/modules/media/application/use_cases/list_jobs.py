"""ListJobsUseCase — the admin Jobs dashboard overview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.dtos.job_dtos import (
    JobOutput,
    JobsOverviewOutput,
)
from src.modules.media.application.use_cases._to_job_run_output import job_run_to_output
from src.modules.media.domain.entities.job_run import JobRunStatus

if TYPE_CHECKING:
    from src.modules.media.application.ports import SchedulerInspectorPort
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class ListJobsUseCase:
    """Merge the live scheduler state with each job's last recorded run.

    The result is the union of jobs currently registered with the
    scheduler and jobs that have history but are no longer scheduled
    (e.g. one that was disabled), so the operator sees both "what will
    run" and "what last ran".
    """

    def __init__(
        self,
        scheduler_inspector: SchedulerInspectorPort,
        media_uow_factory: MediaUnitOfWorkFactory,
    ) -> None:
        self._inspector = scheduler_inspector
        self._media_uow_factory = media_uow_factory

    async def execute(self) -> JobsOverviewOutput:
        """Return the dashboard overview (live schedule + last run per job)."""
        snapshot = self._inspector.snapshot()

        async with self._media_uow_factory() as uow:
            latest = await uow.job_runs.latest_per_job()

        last_by_job = {run.job_id: run for run in latest}
        live_by_job = {job.job_id: job for job in snapshot.jobs}

        jobs = [
            JobOutput(
                job_id=job_id,
                scheduled=job_id in live_by_job,
                schedule=live_by_job[job_id].schedule if job_id in live_by_job else None,
                next_run_at=live_by_job[job_id].next_run_at if job_id in live_by_job else None,
                running=(
                    job_id in last_by_job and last_by_job[job_id].status == JobRunStatus.RUNNING
                ),
                last_run=(
                    job_run_to_output(last_by_job[job_id]) if job_id in last_by_job else None
                ),
            )
            for job_id in sorted(set(live_by_job) | set(last_by_job))
        ]
        return JobsOverviewOutput(scheduler_running=snapshot.running, jobs=jobs)


__all__ = ["ListJobsUseCase"]
