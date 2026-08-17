"""Admin REST routes for intro-detection run history (audit)."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.intro_detection_run_dtos import (
    GetIntroDetectionRunInput,
    ListIntroDetectionRunsInput,
)
from src.modules.media.application.use_cases.get_intro_detection_run import (
    GetIntroDetectionRunUseCase,
)
from src.modules.media.application.use_cases.list_intro_detection_runs import (
    ListIntroDetectionRunsUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Intro Detection"])


@router.get("/intro-detection/runs")
@inject
async def list_intro_detection_runs(
    season_id: str | None = None,
    series_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListIntroDetectionRunsUseCase = Depends(
        Provide[ApplicationContainer.media.list_intro_detection_runs],
    ),
) -> dict[str, Any]:
    """List intro-detection runs newest-first (optionally per season/series)."""
    rows = await use_case.execute(
        ListIntroDetectionRunsInput(
            season_id=season_id,
            series_id=series_id,
            limit=limit,
            offset=offset,
        ),
    )
    return api_list([asdict(row) for row in rows])


@router.get("/intro-detection/runs/{run_id}")
@inject
async def get_intro_detection_run(
    run_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetIntroDetectionRunUseCase = Depends(
        Provide[ApplicationContainer.media.get_intro_detection_run],
    ),
) -> dict[str, Any]:
    """Fetch one intro-detection run with full per-episode detail."""
    output = await use_case.execute(GetIntroDetectionRunInput(run_id=run_id))
    return api_single("intro_detection_run", asdict(output))


__all__ = ["router"]
