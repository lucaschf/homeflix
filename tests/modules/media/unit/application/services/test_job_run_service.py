"""Tests for JobRunService (the scheduler job recorder)."""

import pytest

from src.modules.media.application.services.job_run_service import JobRunService
from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.domain.value_objects.job_run_id import JobRunId


class _FakeJobRuns:
    def __init__(self) -> None:
        self.saved: list[JobRun] = []
        self.pruned: list[tuple[str, int]] = []

    async def save(self, run: JobRun) -> JobRun:
        if run.id is None:
            run = run.with_updates(id=JobRunId.generate())
        self.saved.append(run)
        return run

    async def find_by_id(self, run_id: JobRunId) -> JobRun | None:
        for run in reversed(self.saved):
            if run.id == run_id:
                return run
        return None

    async def prune(self, job_id: str, *, keep: int) -> int:
        self.pruned.append((job_id, keep))
        return 0


class _FakeUoW:
    def __init__(self, job_runs: _FakeJobRuns) -> None:
        self.job_runs = job_runs

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _service() -> tuple[JobRunService, _FakeJobRuns]:
    repo = _FakeJobRuns()
    service = JobRunService(media_uow_factory=lambda: _FakeUoW(repo))  # type: ignore[arg-type]
    return service, repo


@pytest.mark.unit
class TestJobRunService:
    @pytest.mark.asyncio
    async def test_records_running_then_succeeded(self) -> None:
        service, repo = _service()
        calls: list[str] = []

        async def work() -> None:
            calls.append("ran")

        await service.record("homeflix:thumbnail-backfill", work)

        assert calls == ["ran"]
        assert repo.saved[0].status == JobRunStatus.RUNNING
        assert repo.saved[-1].status == JobRunStatus.SUCCEEDED
        assert repo.pruned == [("homeflix:thumbnail-backfill", 100)]

    @pytest.mark.asyncio
    async def test_records_failure_without_propagating(self) -> None:
        service, repo = _service()

        async def boom() -> None:
            raise RuntimeError("kaboom")

        # Must not raise — a crashing job cannot take down the scheduler.
        await service.record("homeflix:intro-detection", boom)

        assert repo.saved[-1].status == JobRunStatus.FAILED
        assert repo.saved[-1].error == "kaboom"
        assert repo.pruned == [("homeflix:intro-detection", 100)]
