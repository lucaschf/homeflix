"""Watch Progress REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.watch_progress.application.dtos import (
    GetContinueWatchingInput,
    GetProgressInput,
    SaveProgressInput,
)
from src.modules.watch_progress.application.use_cases import (
    ClearProgressUseCase,
    GetContinueWatchingUseCase,
    GetProgressUseCase,
    SaveProgressUseCase,
)
from src.modules.watch_progress.application.use_cases.clear_progress import (
    ClearProgressInput,
)
from src.modules.watch_progress.application.use_cases.clear_series_progress import (
    ClearSeriesProgressInput,
    ClearSeriesProgressUseCase,
)
from src.modules.watch_progress.presentation.dependencies import resolve_profile_id

router = APIRouter(prefix="/api/v1/progress", tags=["Watch Progress"])


# -- Schemas -------------------------------------------------------------------


class SaveProgressRequest(BaseModel):
    """Request body for saving watch progress."""

    media_id: str
    media_type: str
    position_seconds: int
    duration_seconds: int
    audio_track: int | None = None
    subtitle_track: int | None = None


# -- Endpoints (continue-watching MUST come before {media_id}) -----------------


@router.get("/continue-watching")
@inject
async def continue_watching(
    limit: int = Query(20, ge=1, le=100),
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetContinueWatchingUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.get_continue_watching],
    ),
) -> dict[str, Any]:
    """List in-progress items for the Continue Watching section."""
    result = await use_case.execute(
        GetContinueWatchingInput(profile_id=profile_id, limit=limit, lang=lang)
    )
    return api_list([asdict(item) for item in result.items])


@router.put("")
@inject
async def save_progress(
    body: SaveProgressRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: SaveProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.save_progress],
    ),
) -> dict[str, Any]:
    """Save or update watch progress for a media item."""
    result = await use_case.execute(
        SaveProgressInput(
            profile_id=profile_id,
            media_id=body.media_id,
            media_type=body.media_type,
            position_seconds=body.position_seconds,
            duration_seconds=body.duration_seconds,
            audio_track=body.audio_track,
            subtitle_track=body.subtitle_track,
        ),
    )
    return api_single("progress", asdict(result))


@router.get("/{media_id}")
@inject
async def get_progress(
    media_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.get_progress],
    ),
) -> dict[str, Any]:
    """Get watch progress for a media item."""
    result = await use_case.execute(GetProgressInput(profile_id=profile_id, media_id=media_id))
    if result is None:
        return api_single("progress", None)
    return api_single("progress", asdict(result))


@router.delete("/series/{series_id}", status_code=204)
@inject
async def clear_series_progress(
    series_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: ClearSeriesProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.clear_series_progress],
    ),
) -> Response:
    """Clear all episode progress for a series in the caller's profile.

    Used by the "dismiss from Continue Watching" action so removing
    a series clears ALL its episode progress at once — otherwise
    deleting one episode's progress just surfaces the next.
    """
    await use_case.execute(ClearSeriesProgressInput(profile_id=profile_id, series_id=series_id))
    return Response(status_code=204)


@router.delete("/{media_id}", status_code=204)
@inject
async def clear_progress(
    media_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: ClearProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.clear_progress],
    ),
) -> Response:
    """Clear watch progress for a media item in the caller's profile."""
    await use_case.execute(ClearProgressInput(profile_id=profile_id, media_id=media_id))
    return Response(status_code=204)


__all__ = ["router"]
