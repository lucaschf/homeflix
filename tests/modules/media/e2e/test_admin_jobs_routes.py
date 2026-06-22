"""End-to-end tests for the admin Jobs dashboard endpoints."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities.job_run import JobRun
from src.modules.media.infrastructure.persistence.repositories.job_run_repository import (
    SqlAlchemyJobRunRepository,
)
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
JOBS_PATH = "/api/v1/admin/jobs"
JOB_RUNS_PATH = "/api/v1/admin/jobs/runs"
JOB_RUN_NOW_PATH = "/api/v1/admin/jobs/homeflix:thumbnail-backfill/run"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


async def _login_as_admin(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
) -> None:
    admin = await seed(email="admin@example.com", is_admin=True)
    await _login(client, admin)


async def _seed_job_run(session_factory: async_sessionmaker[AsyncSession], job_id: str) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyJobRunRepository(session)
        await repo.save(JobRun.start(job_id).succeed())
        await session.commit()


@pytest.mark.e2e
class TestAdminJobsAuth:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        assert (await client.get(JOBS_PATH)).status_code == 401
        assert (await client.get(JOB_RUNS_PATH)).status_code == 401
        assert (await client.post(JOB_RUN_NOW_PATH)).status_code == 401

    async def test_member_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)
        assert (await client.get(JOBS_PATH)).status_code == 403
        assert (await client.post(JOB_RUN_NOW_PATH)).status_code == 403


@pytest.mark.e2e
class TestAdminJobsOverview:
    async def test_overview_shape_with_no_history(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        response = await client.get(JOBS_PATH)

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "jobs_overview"
        assert body["data"]["scheduler_running"] is False
        assert body["data"]["jobs"] == []
        assert body["data"]["executions_24h"] == 0
        assert body["data"]["failures_24h"] == 0

    async def test_overview_surfaces_recorded_job_as_last_run(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        await _seed_job_run(session_factory, "homeflix:thumbnail-backfill")

        body = (await client.get(JOBS_PATH)).json()

        (job,) = body["data"]["jobs"]
        assert job["job_id"] == "homeflix:thumbnail-backfill"
        assert job["scheduled"] is False  # scheduler not started in e2e
        assert job["running"] is False
        assert job["last_run"]["status"] == "succeeded"
        assert job["recent_runs"] == ["succeeded"]
        assert body["data"]["executions_24h"] == 1
        assert body["data"]["failures_24h"] == 0


@pytest.mark.e2e
class TestAdminJobTrigger:
    async def test_run_now_unscheduled_job_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        # The scheduler isn't started in e2e, so nothing is registered
        # and "run now" reports the job as not scheduled.
        await _login_as_admin(client, seed_user_with_profile)

        response = await client.post(JOB_RUN_NOW_PATH)

        assert response.status_code == 404


@pytest.mark.e2e
class TestAdminJobRunsHistory:
    async def test_empty_history_returns_empty_list(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        response = await client.get(JOB_RUNS_PATH)

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "list"
        assert body["data"] == []

    async def test_history_returns_seeded_run(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        await _seed_job_run(session_factory, "homeflix:credits-detection")

        body = (
            await client.get(JOB_RUNS_PATH, params={"job_id": "homeflix:credits-detection"})
        ).json()

        assert len(body["data"]) == 1
        assert body["data"][0]["job_id"] == "homeflix:credits-detection"
        assert body["data"][0]["status"] == "succeeded"
        assert body["data"][0]["duration_ms"] is not None
