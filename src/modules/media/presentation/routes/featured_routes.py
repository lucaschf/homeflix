"""Featured media REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.featured_dtos import GetFeaturedInput
from src.modules.media.application.use_cases.get_featured_media import GetFeaturedMediaUseCase

router = APIRouter(prefix="/api/v1/featured", tags=["Featured"])


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_featured(
    type: str = Query("all", pattern="^(all|movie|series)$"),
    limit: int = Query(6, ge=1, le=20),
    lang: str = "en",
    use_case: GetFeaturedMediaUseCase = Depends(
        Provide[ApplicationContainer.media.get_featured_media],
    ),
) -> dict[str, Any]:
    """Get random featured media for the hero banner."""
    items = await use_case.execute(GetFeaturedInput(media_type=type, limit=limit, lang=lang))
    return {
        "type": "list",
        "data": [asdict(item) for item in items],
    }


__all__ = ["router"]
