"""ListJobsUseCase — the admin Jobs dashboard overview."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
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

# How many recent outcomes feed each job's run-health strip.
_RUN_STRIP_DEPTH = 8

# Window for the dashboard's "executions / failures (24 h)" tiles.
_RECENT_WINDOW = timedelta(hours=24)

# Outcomes that count as a failure on the dashboard.
_FAILURE_STATUSES = (JobRunStatus.FAILED, JobRunStatus.INTERRUPTED)


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
        cutoff = datetime.now(UTC) - _RECENT_WINDOW

        async with self._media_uow_factory() as uow:
            recent = await uow.job_runs.recent_per_job(limit=_RUN_STRIP_DEPTH)
            executions_24h = await uow.job_runs.count(since=cutoff)
            failures_24h = await uow.job_runs.count(
                since=cutoff,
                statuses=_FAILURE_STATUSES,
            )

        # ``recent_per_job`` returns newest-first within each job; the
        # first row per job is therefore its last run.
        recent_by_job: dict[str, list] = defaultdict(list)
        for run in recent:
            recent_by_job[run.job_id].append(run)
        last_by_job = {job_id: runs[0] for job_id, runs in recent_by_job.items()}
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
                # Oldest-first so the strip reads left (old) to right (new).
                recent_runs=[run.status.value for run in reversed(recent_by_job.get(job_id, []))],
            )
            for job_id in sorted(set(live_by_job) | set(last_by_job))
        ]
        return JobsOverviewOutput(
            scheduler_running=snapshot.running,
            jobs=jobs,
            executions_24h=executions_24h,
            failures_24h=failures_24h,
        )


__all__ = ["ListJobsUseCase"]
