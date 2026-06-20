"""Tests for ListJobsUseCase (Jobs dashboard overview)."""

import pytest

from src.modules.media.application.ports import (
    ScheduledJob,
    SchedulerInspectorPort,
    SchedulerSnapshot,
)
from src.modules.media.application.use_cases.list_jobs import ListJobsUseCase
from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.domain.value_objects.job_run_id import JobRunId


class _FakeInspector(SchedulerInspectorPort):
    def __init__(self, snapshot: SchedulerSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> SchedulerSnapshot:
        return self._snapshot


class _FakeJobRuns:
    def __init__(self, latest: list[JobRun]) -> None:
        self._latest = latest

    async def latest_per_job(self) -> list[JobRun]:
        return self._latest


class _FakeUoW:
    def __init__(self, job_runs: _FakeJobRuns) -> None:
        self.job_runs = job_runs

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _run(job_id: str, status: JobRunStatus) -> JobRun:
    run = JobRun.start(job_id).with_updates(id=JobRunId.generate())
    return run if status == JobRunStatus.RUNNING else run.with_updates(status=status)


def _use_case(snapshot: SchedulerSnapshot, latest: list[JobRun]) -> ListJobsUseCase:
    return ListJobsUseCase(
        scheduler_inspector=_FakeInspector(snapshot),
        media_uow_factory=lambda: _FakeUoW(_FakeJobRuns(latest)),  # type: ignore[arg-type]
    )


@pytest.mark.unit
class TestListJobs:
    @pytest.mark.asyncio
    async def test_merges_live_schedule_with_last_run(self) -> None:
        snapshot = SchedulerSnapshot(
            running=True,
            jobs=[ScheduledJob(job_id="job-a", next_run_at="2026-06-20T10:00:00", schedule="i")],
        )
        use_case = _use_case(snapshot, [_run("job-a", JobRunStatus.SUCCEEDED)])

        out = await use_case.execute()

        assert out.scheduler_running is True
        (job,) = out.jobs
        assert job.job_id == "job-a"
        assert job.scheduled is True
        assert job.next_run_at == "2026-06-20T10:00:00"
        assert job.running is False
        assert job.last_run is not None
        assert job.last_run.status == "succeeded"

    @pytest.mark.asyncio
    async def test_flags_running_from_last_run_status(self) -> None:
        snapshot = SchedulerSnapshot(
            running=True,
            jobs=[ScheduledJob(job_id="job-a", next_run_at=None, schedule="i")],
        )
        use_case = _use_case(snapshot, [_run("job-a", JobRunStatus.RUNNING)])

        out = await use_case.execute()

        assert out.jobs[0].running is True

    @pytest.mark.asyncio
    async def test_includes_unscheduled_jobs_that_have_history(self) -> None:
        # A job with history but no live registration (e.g. now disabled).
        snapshot = SchedulerSnapshot(running=True, jobs=[])
        use_case = _use_case(snapshot, [_run("retired-job", JobRunStatus.SUCCEEDED)])

        out = await use_case.execute()

        (job,) = out.jobs
        assert job.job_id == "retired-job"
        assert job.scheduled is False
        assert job.schedule is None
        assert job.last_run is not None
