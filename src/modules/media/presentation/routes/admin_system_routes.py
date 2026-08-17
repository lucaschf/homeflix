"""Admin REST API routes for the System area (HLS cache, health)."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.use_cases.clear_hls_cache_global import (
    ClearHlsCacheGlobalUseCase,
)
from src.modules.media.application.use_cases.get_hls_cache_stats import (
    GetHlsCacheStatsUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — System"])


@router.get("/hls-cache")
@inject
async def get_hls_cache_stats(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetHlsCacheStatsUseCase = Depends(
        Provide[ApplicationContainer.media.get_hls_cache_stats],
    ),
) -> dict[str, Any]:
    """Return current HLS cache size, configured limit and last-cleared.

    Drives the admin System page's occupancy card. Walks the cache
    root server-side — fine for an on-demand call, not something
    the operator polls in a tight loop.
    """
    stats = use_case.execute()
    return api_single(
        "hls_cache_stats",
        {
            "size_bytes": stats.size_bytes,
            "max_bytes": stats.max_bytes,
            "last_cleared_at": (
                stats.last_cleared_at.isoformat() if stats.last_cleared_at else None
            ),
        },
    )


@router.delete("/hls-cache", status_code=204)
@inject
async def clear_hls_cache_global(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ClearHlsCacheGlobalUseCase = Depends(
        Provide[ApplicationContainer.media.clear_hls_cache_global],
    ),
) -> None:
    """Wipe every cached HLS bucket.

    Distinct from the per-movie clear under ``/stream/...`` — the
    admin button hits this global endpoint when the operator wants
    a clean slate (e.g. after changing a transcode setting and
    wanting freshly-generated segments going forward).
    """
    use_case.execute()


__all__ = ["router"]
