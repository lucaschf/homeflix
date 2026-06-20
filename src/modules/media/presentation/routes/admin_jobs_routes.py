"""Admin REST API routes for the background-jobs dashboard."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.application.dtos.job_dtos import ListJobRunsInput
from src.modules.media.application.use_cases.list_job_runs import ListJobRunsUseCase
from src.modules.media.application.use_cases.list_jobs import ListJobsUseCase

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Jobs"])


@router.get("/jobs")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_admin_jobs(
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListJobsUseCase = Depends(Provide[ApplicationContainer.list_jobs]),
) -> dict[str, Any]:
    """Overview of every background job: live schedule + last run + running-now.

    Merges the scheduler's live registry (next run, schedule) with each
    job's most recent recorded execution, so a single call drives the
    admin Jobs dashboard.
    """
    overview = await use_case.execute()
    return api_single("jobs_overview", asdict(overview))


@router.get("/jobs/runs")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_admin_job_runs(
    job_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListJobRunsUseCase = Depends(
        Provide[ApplicationContainer.media.list_job_runs],
    ),
) -> dict[str, Any]:
    """Paginated job-execution history, newest-first, optionally per job."""
    rows = await use_case.execute(
        ListJobRunsInput(job_id=job_id, limit=limit, offset=offset),
    )
    return api_list([asdict(r) for r in rows])


__all__ = ["router"]
