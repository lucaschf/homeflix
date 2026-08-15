"""Admin REST route for multi-episode file segments (ADR-030).

Some mini-series ship several episodes concatenated in one physical file.
This endpoint lets an operator declare the per-episode time windows so each
episode streams just its range of the shared file, without splitting it on
disk. Enrichment already created the episodes; this only attaches segmented
file variants to them.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.segment_dtos import (
    DefineEpisodeSegmentsInput,
    EpisodeSegmentSpec,
)
from src.modules.media.application.use_cases.define_episode_segments import (
    DefineEpisodeSegmentsUseCase,
)
from src.modules.media.presentation.schemas.segment_schemas import (
    DefineEpisodeSegmentsRequest,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Segments"])


@router.post("/series/{series_id}/file-segments")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def define_episode_segments(
    series_id: str,
    body: DefineEpisodeSegmentsRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: DefineEpisodeSegmentsUseCase = Depends(
        Provide[ApplicationContainer.media.define_episode_segments],
    ),
) -> dict[str, Any]:
    """Attach per-episode file segments to a season's episodes.

    Every episode named in ``segments`` gets a primary file variant pointing
    at the shared ``file_path``, bounded by its ``[start_seconds, end_seconds)``
    window, and its duration is set to that window's length. Overlapping
    segments, a window past the file's duration, or an unknown episode surface
    as 4xx.
    """
    result = await use_case.execute(
        DefineEpisodeSegmentsInput(
            series_id=series_id,
            season_number=body.season_number,
            file_path=body.file_path,
            segments=[
                EpisodeSegmentSpec(
                    episode_number=item.episode_number,
                    start_seconds=item.start_seconds,
                    end_seconds=item.end_seconds,
                )
                for item in body.segments
            ],
        ),
    )
    return api_single("file_segments", asdict(result))


__all__ = ["router"]
