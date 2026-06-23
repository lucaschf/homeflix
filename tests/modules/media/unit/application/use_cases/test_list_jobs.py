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
    def __init__(self, recent: list[JobRun]) -> None:
        # Stored newest-first within each job, matching the real repo.
        self._recent = recent

    async def recent_per_job(self, *, limit: int) -> list[JobRun]:
        by_job: dict[str, list[JobRun]] = {}
        for run in self._recent:
            by_job.setdefault(run.job_id, []).append(run)
        out: list[JobRun] = []
        for runs in by_job.values():
            out.extend(runs[:limit])
        return out

    async def count(self, *, job_id=None, since=None, statuses=None) -> int:
        runs = self._recent
        if statuses is not None:
            allowed = set(statuses)
            runs = [r for r in runs if r.status in allowed]
        return len(runs)


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


def _use_case(snapshot: SchedulerSnapshot, recent: list[JobRun]) -> ListJobsUseCase:
    return ListJobsUseCase(
        scheduler_inspector=_FakeInspector(snapshot),
        media_uow_factory=lambda: _FakeUoW(_FakeJobRuns(recent)),  # type: ignore[arg-type]
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

    @pytest.mark.asyncio
    async def test_recent_runs_are_oldest_first(self) -> None:
        snapshot = SchedulerSnapshot(
            running=True,
            jobs=[ScheduledJob(job_id="job-a", next_run_at=None, schedule="i")],
        )
        # Repo order is newest-first: failed (newest) then succeeded.
        recent = [
            _run("job-a", JobRunStatus.FAILED),
            _run("job-a", JobRunStatus.SUCCEEDED),
        ]
        use_case = _use_case(snapshot, recent)

        out = await use_case.execute()

        # Strip reads left (old) to right (new): the failure is last.
        assert out.jobs[0].recent_runs == ["succeeded", "failed"]
        assert out.jobs[0].last_run is not None
        assert out.jobs[0].last_run.status == "failed"

    @pytest.mark.asyncio
    async def test_aggregates_executions_and_failures(self) -> None:
        snapshot = SchedulerSnapshot(running=True, jobs=[])
        recent = [
            _run("job-a", JobRunStatus.SUCCEEDED),
            _run("job-a", JobRunStatus.FAILED),
            _run("job-b", JobRunStatus.INTERRUPTED),
        ]
        use_case = _use_case(snapshot, recent)

        out = await use_case.execute()

        assert out.executions_24h == 3
        assert out.failures_24h == 2
