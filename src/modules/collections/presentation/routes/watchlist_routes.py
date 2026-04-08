"""Watchlist REST API routes."""

from dataclasses import asdict
from typing import Any, Literal

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.config.containers import ApplicationContainer
from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    ToggleWatchlistInput,
)
from src.modules.collections.application.use_cases import (
    CheckWatchlistUseCase,
    GetWatchlistUseCase,
    ToggleWatchlistUseCase,
)

router = APIRouter(prefix="/api/v1/watchlist", tags=["Watchlist"])


# -- Schemas -------------------------------------------------------------------


class ToggleWatchlistRequest(BaseModel):
    """Request body for toggling a watchlist item."""

    media_id: str
    media_type: Literal["movie", "series"]


# -- Endpoints -----------------------------------------------------------------


@router.post("/toggle")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def toggle_watchlist(
    body: ToggleWatchlistRequest,
    use_case: ToggleWatchlistUseCase = Depends(
        Provide[ApplicationContainer.collections.toggle_watchlist],
    ),
) -> dict[str, Any]:
    """Add or remove a media item from the watchlist."""
    result = await use_case.execute(
        ToggleWatchlistInput(
            media_id=body.media_id,
            media_type=body.media_type,
        ),
    )
    return {"type": "watchlist", "data": asdict(result)}


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_watchlist(
    limit: int = Query(100, ge=1, le=500),
    lang: str = "en",
    use_case: GetWatchlistUseCase = Depends(
        Provide[ApplicationContainer.collections.get_watchlist],
    ),
) -> dict[str, Any]:
    """List all items in the user's watchlist."""
    items = await use_case.execute(GetWatchlistInput(limit=limit, lang=lang))
    return {
        "type": "list",
        "data": [asdict(item) for item in items],
    }


@router.get("/check/{media_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def check_watchlist(
    media_id: str,
    use_case: CheckWatchlistUseCase = Depends(
        Provide[ApplicationContainer.collections.check_watchlist],
    ),
) -> dict[str, Any]:
    """Check if a media item is in the watchlist."""
    in_list = await use_case.execute(media_id)
    return {"type": "watchlist", "data": {"in_list": in_list}}


__all__ = ["router"]
