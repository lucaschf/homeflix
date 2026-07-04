"""Admin REST routes for subtitle-OCR run history (audit)."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.subtitle_ocr_run_dtos import (
    GetSubtitleOcrRunInput,
    ListSubtitleOcrRunsInput,
)
from src.modules.media.application.use_cases.get_subtitle_ocr_run import (
    GetSubtitleOcrRunUseCase,
)
from src.modules.media.application.use_cases.list_subtitle_ocr_runs import (
    ListSubtitleOcrRunsUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Subtitle OCR"])


@router.get("/subtitle-ocr/runs")
@inject
async def list_subtitle_ocr_runs(
    media_kind: str | None = None,
    media_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListSubtitleOcrRunsUseCase = Depends(
        Provide[ApplicationContainer.media.list_subtitle_ocr_runs],
    ),
) -> dict[str, Any]:
    """List subtitle-OCR runs newest-first (optionally per media kind/id)."""
    rows = await use_case.execute(
        ListSubtitleOcrRunsInput(
            media_kind=media_kind,
            media_id=media_id,
            limit=limit,
            offset=offset,
        ),
    )
    return api_list([asdict(row) for row in rows])


@router.get("/subtitle-ocr/runs/{run_id}")
@inject
async def get_subtitle_ocr_run(
    run_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetSubtitleOcrRunUseCase = Depends(
        Provide[ApplicationContainer.media.get_subtitle_ocr_run],
    ),
) -> dict[str, Any]:
    """Fetch one subtitle-OCR run with full per-track detail."""
    output = await use_case.execute(GetSubtitleOcrRunInput(run_id=run_id))
    return api_single("subtitle_ocr_run", asdict(output))


__all__ = ["router"]
