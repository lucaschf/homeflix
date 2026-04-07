"""Watch Progress REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

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


@router.get("/continue-watching")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def continue_watching(
    limit: int = 20,
    lang: str = "en",
    use_case: GetContinueWatchingUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.get_continue_watching],
    ),
) -> dict[str, Any]:
    """List in-progress items for the Continue Watching section."""
    result = await use_case.execute(GetContinueWatchingInput(limit=limit, lang=lang))
    return {
        "type": "list",
        "data": [asdict(item) for item in result.items],
    }


@router.put("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def save_progress(
    body: SaveProgressRequest,
    use_case: SaveProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.save_progress],
    ),
) -> dict[str, Any]:
    """Save or update watch progress for a media item."""
    result = await use_case.execute(
        SaveProgressInput(
            media_id=body.media_id,
            media_type=body.media_type,
            position_seconds=body.position_seconds,
            duration_seconds=body.duration_seconds,
            audio_track=body.audio_track,
            subtitle_track=body.subtitle_track,
        ),
    )
    return {"type": "progress", "data": asdict(result)}


@router.get("/{media_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_progress(
    media_id: str,
    use_case: GetProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.get_progress],
    ),
) -> dict[str, Any]:
    """Get watch progress for a media item."""
    result = await use_case.execute(GetProgressInput(media_id=media_id))
    if result is None:
        return {"type": "progress", "data": None}
    return {"type": "progress", "data": asdict(result)}


@router.delete("/{media_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def clear_progress(
    media_id: str,
    use_case: ClearProgressUseCase = Depends(
        Provide[ApplicationContainer.watch_progress.clear_progress],
    ),
) -> Response:
    """Clear watch progress for a media item."""
    await use_case.execute(ClearProgressInput(media_id=media_id))
    return Response(status_code=204)


__all__ = ["router"]
