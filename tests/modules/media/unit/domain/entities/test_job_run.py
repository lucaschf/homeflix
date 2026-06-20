"""Tests for the JobRun aggregate."""

import pytest

from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus


@pytest.mark.unit
class TestJobRunLifecycle:
    def test_start_opens_running_row(self) -> None:
        run = JobRun.start("homeflix:thumbnail-backfill")

        assert run.job_id == "homeflix:thumbnail-backfill"
        assert run.status == JobRunStatus.RUNNING
        assert run.finished_at is None
        assert run.duration_ms is None

    def test_succeed_sets_finished_and_status(self) -> None:
        run = JobRun.start("job").succeed()

        assert run.status == JobRunStatus.SUCCEEDED
        assert run.finished_at is not None
        assert run.error is None
        assert run.duration_ms is not None
        assert run.duration_ms >= 0

    def test_fail_records_truncated_error(self) -> None:
        run = JobRun.start("job").fail("x" * 5000)

        assert run.status == JobRunStatus.FAILED
        assert run.finished_at is not None
        assert run.error is not None
        assert len(run.error) == 2000

    def test_mark_interrupted_closes_row(self) -> None:
        run = JobRun.start("job").mark_interrupted()

        assert run.status == JobRunStatus.INTERRUPTED
        assert run.finished_at is not None
        assert run.error is not None
