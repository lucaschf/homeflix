"""Admin REST API routes for the Overview dashboard."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.media.application.use_cases.get_library_usage import (
    GetLibraryUsageUseCase,
)
from src.modules.media.application.use_cases.get_now_playing import GetNowPlayingUseCase
from src.modules.media.application.use_cases.get_overview_stats import (
    GetOverviewStatsUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Overview"])


@router.get("/overview/stats")
@inject
async def get_admin_overview_stats(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetOverviewStatsUseCase = Depends(
        Provide[ApplicationContainer.media.get_overview_stats],
    ),
) -> dict[str, Any]:
    """Aggregate every Overview stat card into a single response.

    The dashboard's headline cards (movies / series / users /
    review queue / last scan) plus the HLS occupancy strip all
    come from this one call so the page settles in a single
    loading transition.
    """
    stats = await use_case.execute()
    return api_single("overview_stats", asdict(stats))


@router.get("/now-playing")
@inject
async def get_admin_now_playing(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetNowPlayingUseCase = Depends(
        Provide[ApplicationContainer.media.get_now_playing],
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


@router.get("/library-usage")
@inject
async def get_admin_library_usage(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetLibraryUsageUseCase = Depends(
        Provide[ApplicationContainer.media.get_library_usage],
    ),
) -> dict[str, Any]:
    """Per-library catalog size (sum of primary-file bytes), largest first.

    Cheap SQL aggregation, not a disk ``du`` — it ranks libraries
    against each other for the "Uso de disco por library" panel. The
    frontend joins ``library_id`` with the libraries list for names.
    """
    usage = await use_case.execute()
    return api_single("library_usage", asdict(usage))


__all__ = ["router"]
