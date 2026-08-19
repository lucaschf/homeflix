"""Admin REST route for the live now-playing panel."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.streaming.application.use_cases.get_now_playing import GetNowPlayingUseCase

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Now Playing"])


@router.get("/now-playing")
@inject
async def get_admin_now_playing(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetNowPlayingUseCase = Depends(
        Provide[ApplicationContainer.streaming.get_now_playing],
    ),
) -> dict[str, Any]:
    """List the playback sessions active on the server right now.

    An in-memory snapshot fed observationally by the streaming path:
    one row per live HLS session with watcher, progress and uplink,
    plus the aggregate ``total_mbps``. An idle server returns an empty
    list — the expected resting state.
    """
    snapshot = await use_case.execute()
    return api_single("now_playing", asdict(snapshot))


__all__ = ["router"]
