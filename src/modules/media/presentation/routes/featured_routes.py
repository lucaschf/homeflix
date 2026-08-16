"""Featured media REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.presentation import api_list
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.featured_dtos import GetFeaturedInput
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase
from src.modules.media.presentation.dependencies import resolve_profile_id

router = APIRouter(prefix="/api/v1/featured", tags=["Featured"])


@router.get("")
@inject
async def get_featured(
    type: str = Query("all", pattern="^(all|movie|series)$"),
    limit: int = Query(6, ge=1, le=20),
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetFeaturedMediaUseCase = Depends(
        Provide[ApplicationContainer.media.get_featured_media],
    ),
) -> dict[str, Any]:
    """Get random featured media for the hero banner."""
    items = await use_case.execute(
        GetFeaturedInput(profile_id=profile_id, media_type=type, limit=limit, lang=lang)
    )
    return api_list([asdict(item) for item in items])


__all__ = ["router"]
