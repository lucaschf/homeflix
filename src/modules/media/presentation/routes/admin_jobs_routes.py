"""Admin REST API routes for the background-jobs dashboard."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.job_dtos import ListJobRunsInput, TriggerJobInput
from src.modules.media.application.use_cases.list_job_runs import ListJobRunsUseCase
from src.modules.media.application.use_cases.list_jobs import ListJobsUseCase
from src.modules.media.application.use_cases.trigger_job import (
    JobNotScheduledError,
    TriggerJobUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Jobs"])


@router.get("/jobs")
@inject
async def list_admin_jobs(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListJobsUseCase = Depends(Provide[ApplicationContainer.list_jobs]),
) -> dict[str, Any]:
    """Overview of every background job: live schedule + last run + running-now.

    Merges the scheduler's live registry (next run, schedule) with each
    job's most recent recorded execution, so a single call drives the
    admin Jobs dashboard.
    """
    overview = await use_case.execute()
    return api_single("jobs_overview", asdict(overview))


@router.get("/jobs/runs")
@inject
async def list_admin_job_runs(
    job_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListJobRunsUseCase = Depends(
        Provide[ApplicationContainer.media.list_job_runs],
    ),
) -> dict[str, Any]:
    """Paginated job-execution history, newest-first, optionally per job."""
    rows = await use_case.execute(
        ListJobRunsInput(job_id=job_id, limit=limit, offset=offset),
    )
    return api_list([asdict(r) for r in rows])


@router.post("/jobs/{job_id}/run", status_code=202)
@inject
async def trigger_admin_job(
    job_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: TriggerJobUseCase = Depends(
        Provide[ApplicationContainer.trigger_job],
    ),
) -> dict[str, Any]:
    """Run a scheduled job immediately ("run now").

    Reschedules the registered job to fire on the next scheduler tick;
    its execution is recorded in ``job_runs`` like any scheduled run, so
    the dashboard reflects it within a poll cycle. Returns 202 with the
    job id; 404 when the job isn't currently scheduled.
    """
    try:
        await use_case.execute(TriggerJobInput(job_id=job_id))
    except JobNotScheduledError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return api_single("job_trigger", {"job_id": job_id, "triggered": True})


__all__ = ["router"]
