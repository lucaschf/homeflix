"""Integration tests for SqlAlchemyJobRunRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities.job_run import JobRun, JobRunStatus
from src.modules.media.infrastructure.persistence.repositories.job_run_repository import (
    SqlAlchemyJobRunRepository,
)


@pytest.mark.integration
class TestSaveAndFind:
    async def test_save_assigns_external_id(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        saved = await repo.save(JobRun.start("homeflix:thumbnail-backfill"))

        assert saved.id is not None
        assert str(saved.id).startswith("job_")
        assert saved.status == JobRunStatus.RUNNING

    async def test_save_updates_in_place_on_terminal(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        opened = await repo.save(JobRun.start("job-x"))

        await repo.save(opened.succeed())
        again = await repo.find_by_id(opened.id)  # type: ignore[arg-type]

        assert again is not None
        assert again.status == JobRunStatus.SUCCEEDED
        assert again.finished_at is not None
        assert again.duration_ms is not None


@pytest.mark.integration
class TestLatestPerJob:
    async def test_returns_most_recent_run_per_job(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        # Two jobs; job-a runs twice, the second finishing failed.
        await repo.save(JobRun.start("job-a").succeed())
        await repo.save(JobRun.start("job-a").fail("boom"))
        await repo.save(JobRun.start("job-b").succeed())

        latest = await repo.latest_per_job()
        by_job = {r.job_id: r for r in latest}

        assert set(by_job) == {"job-a", "job-b"}
        assert by_job["job-a"].status == JobRunStatus.FAILED
        assert by_job["job-b"].status == JobRunStatus.SUCCEEDED


@pytest.mark.integration
class TestListAndStatus:
    async def test_list_paginated_filters_by_job_id(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        await repo.save(JobRun.start("job-a").succeed())
        await repo.save(JobRun.start("job-b").succeed())

        only_a = await repo.list_paginated(job_id="job-a")

        assert len(only_a) == 1
        assert only_a[0].job_id == "job-a"

    async def test_list_by_status_returns_running(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        await repo.save(JobRun.start("job-a"))  # running
        await repo.save(JobRun.start("job-b").succeed())

        running = await repo.list_by_status(JobRunStatus.RUNNING)

        assert len(running) == 1
        assert running[0].job_id == "job-a"


@pytest.mark.integration
class TestPrune:
    async def test_prune_soft_deletes_all_but_newest(self, db_session: AsyncSession) -> None:
        repo = SqlAlchemyJobRunRepository(db_session)
        for _ in range(5):
            await repo.save(JobRun.start("job-a").succeed())

        pruned = await repo.prune("job-a", keep=2)

        assert pruned == 3
        remaining = await repo.list_paginated(job_id="job-a", limit=100)
        assert len(remaining) == 2
        assert await repo.count(job_id="job-a") == 2
