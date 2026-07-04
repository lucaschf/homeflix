"""Admin REST routes for subtitle-OCR runs (audit + manual trigger)."""

import asyncio
from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.config.logging import get_logger
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.subtitle_ocr_run_dtos import (
    GetSubtitleOcrRunInput,
    ListSubtitleOcrRunsInput,
    RunSubtitleOcrInput,
)
from src.modules.media.application.use_cases.get_subtitle_ocr_run import (
    GetSubtitleOcrRunUseCase,
)
from src.modules.media.application.use_cases.list_subtitle_ocr_runs import (
    ListSubtitleOcrRunsUseCase,
)
from src.modules.media.application.use_cases.run_subtitle_ocr_for_media import (
    RunSubtitleOcrForMediaUseCase,
)

_logger = get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Subtitle OCR"])

# Strong references to in-flight manual-OCR tasks so the event loop's weak
# reference doesn't GC a running OCR (mirrors the eager-thumbnail pattern).
_manual_ocr_tasks: set[asyncio.Task[Any]] = set()


def _fire_manual_ocr(
    use_case: RunSubtitleOcrForMediaUseCase, media_kind: str, media_id: str
) -> None:
    """Launch a manual OCR run in the background (fire-and-forget).

    OCR takes minutes, so the request returns 202 immediately; the run is
    recorded on completion and surfaced via the runs list. Exceptions are
    logged — a not-found media never reaches here (the UI triggers only on
    titles it displays), and OCR failures are recorded as FAILED runs.
    """

    async def _run() -> None:
        try:
            await use_case.execute(RunSubtitleOcrInput(media_kind=media_kind, media_id=media_id))
        except Exception:
            _logger.exception(
                "[subtitle-ocr] manual trigger failed",
                extra={"media_kind": media_kind, "media_id": media_id},
            )

    task = asyncio.create_task(_run())
    _manual_ocr_tasks.add(task)
    task.add_done_callback(_manual_ocr_tasks.discard)


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


@router.post("/subtitle-ocr/movies/{movie_id}/run", status_code=202)
@inject
async def run_movie_subtitle_ocr(
    movie_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: RunSubtitleOcrForMediaUseCase = Depends(
        Provide[ApplicationContainer.media.run_subtitle_ocr_for_media],
    ),
) -> dict[str, Any]:
    """Trigger OCR for one movie now (best-effort, runs in the background)."""
    _fire_manual_ocr(use_case, "movie", movie_id)
    return api_single(
        "subtitle_ocr_trigger",
        {"media_kind": "movie", "media_id": movie_id, "triggered": True},
    )


@router.post("/subtitle-ocr/episodes/{episode_id}/run", status_code=202)
@inject
async def run_episode_subtitle_ocr(
    episode_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: RunSubtitleOcrForMediaUseCase = Depends(
        Provide[ApplicationContainer.media.run_subtitle_ocr_for_media],
    ),
) -> dict[str, Any]:
    """Trigger OCR for one episode now (best-effort, runs in the background)."""
    _fire_manual_ocr(use_case, "episode", episode_id)
    return api_single(
        "subtitle_ocr_trigger",
        {"media_kind": "episode", "media_id": episode_id, "triggered": True},
    )


__all__ = ["router"]
