"""Series REST API routes."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.building_blocks.presentation import Pagination, api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.intro_dtos import (
    ClearEpisodeIntroInput,
    SetEpisodeIntroInput,
)
from src.modules.media.application.dtos.media_file_dtos import (
    AddFileVariantInput,
    GetFileVariantsInput,
    RemoveFileVariantInput,
    SetPrimaryFileInput,
)
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput, ListSeriesInput
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.clear_episode_intro import ClearEpisodeIntroUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.set_episode_intro import SetEpisodeIntroUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.presentation.schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetIntroRequest,
    SetPrimaryFileRequest,
)

router = APIRouter(prefix="/api/v1/series", tags=["Series"])


# ── Series endpoints ────────────────────────────────────────────────


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_series(
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    include_count: bool = False,
    lang: str = "en",
    use_case: ListSeriesUseCase = Depends(
        Provide[ApplicationContainer.media.list_series],
    ),
) -> dict[str, Any]:
    """List one cursor-paginated page of series.

    Same query-param contract as ``GET /api/v1/movies`` — see that
    endpoint for the full description of ``cursor``, ``limit``,
    ``include_count``, and the response shape.
    """
    clamped_limit = max(1, min(limit, MAX_PAGE_SIZE))
    result = await use_case.execute(
        ListSeriesInput(
            cursor=cursor,
            limit=clamped_limit,
            include_total=include_count,
            lang=lang,
        )
    )
    extras: dict[str, Any] | None = (
        {"total_count": result.total_count} if result.total_count is not None else None
    )
    return api_list(
        [_dataclass_to_dict(s) for s in result.series],
        pagination=Pagination(has_more=result.has_more, next_cursor=result.next_cursor),
        metadata_extras=extras,
    )


@router.get("/{series_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_series(
    series_id: str,
    lang: str = "en",
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> dict[str, Any]:
    """Get a series by ID (includes full season/episode hierarchy)."""
    result = await use_case.execute(GetSeriesByIdInput(series_id=series_id, lang=lang))
    return api_single("series", _dataclass_to_dict(result))


# ── Episode file variant endpoints ──────────────────────────────────


@router.get("/episodes/{episode_id}/files")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_episode_file_variants(
    episode_id: str,
    use_case: GetFileVariantsUseCase = Depends(
        Provide[ApplicationContainer.media.get_file_variants],
    ),
) -> dict[str, Any]:
    """List all file variants of an episode."""
    result = await use_case.execute(GetFileVariantsInput(media_id=episode_id))
    return api_list([_dataclass_to_dict(f) for f in result])


@router.post("/episodes/{episode_id}/files", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def add_episode_file_variant(
    episode_id: str,
    body: AddFileVariantRequest,
    use_case: AddFileVariantUseCase = Depends(
        Provide[ApplicationContainer.media.add_file_variant],
    ),
) -> dict[str, Any]:
    """Add a file variant to an episode."""
    result = await use_case.execute(
        AddFileVariantInput(
            media_id=episode_id,
            file_path=body.file_path,
            file_size=body.file_size,
            resolution=body.resolution,
            video_codec=body.video_codec,
            video_bitrate=body.video_bitrate,
            hdr_format=body.hdr_format,
            is_primary=body.is_primary,
        ),
    )
    return api_single("media_file", _dataclass_to_dict(result))


@router.delete("/episodes/{episode_id}/files", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def remove_episode_file_variant(
    episode_id: str,
    body: RemoveFileVariantRequest,
    use_case: RemoveFileVariantUseCase = Depends(
        Provide[ApplicationContainer.media.remove_file_variant],
    ),
) -> None:
    """Remove a file variant from an episode."""
    await use_case.execute(
        RemoveFileVariantInput(media_id=episode_id, file_path=body.file_path),
    )


@router.put("/episodes/{episode_id}/files/primary")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def set_episode_primary_file(
    episode_id: str,
    body: SetPrimaryFileRequest,
    use_case: SetPrimaryFileUseCase = Depends(
        Provide[ApplicationContainer.media.set_primary_file],
    ),
) -> dict[str, Any]:
    """Set a file variant as primary for an episode."""
    result = await use_case.execute(
        SetPrimaryFileInput(media_id=episode_id, file_path=body.file_path),
    )
    return api_list([_dataclass_to_dict(f) for f in result])


@router.put("/episodes/{episode_id}/intro")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def set_episode_intro(
    episode_id: str,
    body: SetIntroRequest,
    use_case: SetEpisodeIntroUseCase = Depends(
        Provide[ApplicationContainer.media.set_episode_intro],
    ),
) -> dict[str, Any]:
    """Set or replace the manual intro marker on an episode.

    Returns the persisted marker. Validation errors (negative bounds,
    end <= start, end > episode duration) surface as 422.
    """
    result = await use_case.execute(
        SetEpisodeIntroInput(
            episode_id=episode_id,
            start_seconds=body.start_seconds,
            end_seconds=body.end_seconds,
        ),
    )
    return api_single("intro", _dataclass_to_dict(result))


@router.delete("/episodes/{episode_id}/intro", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def clear_episode_intro(
    episode_id: str,
    use_case: ClearEpisodeIntroUseCase = Depends(
        Provide[ApplicationContainer.media.clear_episode_intro],
    ),
) -> None:
    """Remove the intro marker from an episode.

    Idempotent — clearing an episode without a marker still returns
    204. The episode rejoins the auto-detection queue on the next
    job tick.
    """
    await use_case.execute(ClearEpisodeIntroInput(episode_id=episode_id))


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a frozen dataclass to a dictionary.

    Args:
        obj: A frozen dataclass instance.

    Returns:
        Dictionary representation.
    """
    from dataclasses import asdict

    return asdict(obj)


__all__ = ["router"]
