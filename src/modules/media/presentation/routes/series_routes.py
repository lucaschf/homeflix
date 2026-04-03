"""Series REST API routes."""

from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.media_file_dtos import (
    AddFileVariantInput,
    GetFileVariantsInput,
    RemoveFileVariantInput,
    SetPrimaryFileInput,
)
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput, ListSeriesInput
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.presentation.schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetPrimaryFileRequest,
)

router = APIRouter(prefix="/api/v1/series", tags=["Series"])


# ── Series endpoints ────────────────────────────────────────────────


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_series(
    limit: int | None = None,
    use_case: ListSeriesUseCase = Depends(
        Provide[ApplicationContainer.media.list_series],
    ),
) -> dict[str, Any]:
    """List all series."""
    result = await use_case.execute(ListSeriesInput(limit=limit))
    return {
        "type": "list",
        "data": [_dataclass_to_dict(s) for s in result.series],
        "metadata": {"total_count": result.total_count},
    }


@router.get("/{series_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_series(
    series_id: str,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> dict[str, Any]:
    """Get a series by ID (includes full season/episode hierarchy)."""
    result = await use_case.execute(GetSeriesByIdInput(series_id=series_id))
    return {
        "type": "series",
        "data": _dataclass_to_dict(result),
    }


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
    return {
        "type": "list",
        "data": [_dataclass_to_dict(f) for f in result],
    }


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
    return {
        "type": "media_file",
        "data": _dataclass_to_dict(result),
    }


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
    return {
        "type": "list",
        "data": [_dataclass_to_dict(f) for f in result],
    }


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
