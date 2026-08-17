"""Admin REST routes for manual credits markers (movies + episodes).

Credits detection is per-file and best-effort, so operators need a way
to correct or remove a marker and to requeue detection. These endpoints
are media-agnostic — the ``media_id`` path param is a movie (mov_xxx) or
episode (epi_xxx) id; the use cases dispatch to the right aggregate.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.credits_dtos import (
    ListCreditsStatusInput,
    ResetCreditsDetectionInput,
    SetCreditsMarkerInput,
)
from src.modules.media.application.use_cases.clear_credits_marker import (
    ClearCreditsMarkerUseCase,
)
from src.modules.media.application.use_cases.list_credits_status import (
    ListCreditsStatusUseCase,
)
from src.modules.media.application.use_cases.reset_credits_detection import (
    ResetCreditsDetectionUseCase,
)
from src.modules.media.application.use_cases.set_credits_marker import SetCreditsMarkerUseCase
from src.modules.media.presentation.schemas.credits_schemas import SetCreditsRequest

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Credits"])


@router.get("/credits/status")
@inject
async def list_credits_status(
    media_type: str = "movie",
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListCreditsStatusUseCase = Depends(
        Provide[ApplicationContainer.media.list_credits_status],
    ),
) -> dict[str, Any]:
    """Observability: titles by credits-detection state + per-state counts.

    ``media_type`` is ``movie`` or ``episode``; ``state`` optionally filters
    by detection state. Returns a single object with the page, total, and
    the unfiltered per-state counts for the filter chips.
    """
    output = await use_case.execute(
        ListCreditsStatusInput(
            media_type=media_type,
            state=state,
            limit=limit,
            offset=offset,
        ),
    )
    return api_single("credits_status", asdict(output))


@router.put("/media/{media_id}/credits")
@inject
async def set_credits_marker(
    media_id: str,
    body: SetCreditsRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: SetCreditsMarkerUseCase = Depends(
        Provide[ApplicationContainer.media.set_credits_marker],
    ),
) -> dict[str, Any]:
    """Set or replace the manual credits marker on a movie/episode.

    Returns the persisted marker. ``start_seconds`` beyond the title's
    duration surfaces as 422.
    """
    result = await use_case.execute(
        SetCreditsMarkerInput(media_id=media_id, start_seconds=body.start_seconds),
    )
    return api_single("credits", asdict(result))


@router.delete("/media/{media_id}/credits", status_code=204)
@inject
async def clear_credits_marker(
    media_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ClearCreditsMarkerUseCase = Depends(
        Provide[ApplicationContainer.media.clear_credits_marker],
    ),
) -> None:
    """Remove the credits marker from a movie/episode.

    Marks the title ``COMPLETED`` with no marker so the job does not
    re-add one. Use the reset endpoint to instead re-run detection.
    """
    await use_case.execute(media_id)


@router.post("/media/{media_id}/credits-detection/reset")
@inject
async def reset_credits_detection(
    media_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ResetCreditsDetectionUseCase = Depends(
        Provide[ApplicationContainer.media.reset_credits_detection],
    ),
) -> dict[str, Any]:
    """Requeue one movie/episode for automatic credits detection.

    Returns the title to ``NOT_STARTED`` so the next job tick reprocesses
    it, clearing an AUTO_DETECTED marker (MANUAL ones are kept).
    """
    result = await use_case.execute(ResetCreditsDetectionInput(media_id=media_id))
    return api_single("credits_detection_reset", asdict(result))


__all__ = ["router"]
