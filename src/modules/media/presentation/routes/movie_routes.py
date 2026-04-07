"""Movie REST API routes."""

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
from src.modules.media.application.dtos.movie_dtos import (
    DeleteMovieInput,
    GetMovieByIdInput,
    ListMoviesInput,
)
from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.delete_movie import DeleteMovieUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase
from src.modules.media.presentation.schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetPrimaryFileRequest,
)

router = APIRouter(prefix="/api/v1/movies", tags=["Movies"])


# ── Movie endpoints ─────────────────────────────────────────────────


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_movies(
    limit: int | None = None,
    use_case: ListMoviesUseCase = Depends(
        Provide[ApplicationContainer.media.list_movies],
    ),
) -> dict[str, Any]:
    """List all movies."""
    result = await use_case.execute(ListMoviesInput(limit=limit))
    return {
        "type": "list",
        "data": [_dataclass_to_dict(m) for m in result.movies],
        "metadata": {"total_count": result.total_count},
    }


@router.get("/{movie_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_movie(
    movie_id: str,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> dict[str, Any]:
    """Get a movie by ID."""
    result = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    return {
        "type": "movie",
        "data": _dataclass_to_dict(result),
    }


@router.delete("/{movie_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_movie(
    movie_id: str,
    use_case: DeleteMovieUseCase = Depends(
        Provide[ApplicationContainer.media.delete_movie],
    ),
) -> None:
    """Soft-delete a movie by ID.

    The movie record is marked as deleted but not physically removed,
    allowing for future recovery if needed.
    """
    await use_case.execute(DeleteMovieInput(movie_id=movie_id))


# ── File variant endpoints ──────────────────────────────────────────


@router.get("/{movie_id}/files")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_file_variants(
    movie_id: str,
    use_case: GetFileVariantsUseCase = Depends(
        Provide[ApplicationContainer.media.get_file_variants],
    ),
) -> dict[str, Any]:
    """List all file variants of a movie."""
    result = await use_case.execute(GetFileVariantsInput(media_id=movie_id))
    return {
        "type": "list",
        "data": [_dataclass_to_dict(f) for f in result],
    }


@router.post("/{movie_id}/files", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def add_file_variant(
    movie_id: str,
    body: AddFileVariantRequest,
    use_case: AddFileVariantUseCase = Depends(
        Provide[ApplicationContainer.media.add_file_variant],
    ),
) -> dict[str, Any]:
    """Add a file variant to a movie."""
    result = await use_case.execute(
        AddFileVariantInput(
            media_id=movie_id,
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


@router.delete("/{movie_id}/files", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def remove_file_variant(
    movie_id: str,
    body: RemoveFileVariantRequest,
    use_case: RemoveFileVariantUseCase = Depends(
        Provide[ApplicationContainer.media.remove_file_variant],
    ),
) -> None:
    """Remove a file variant from a movie."""
    await use_case.execute(
        RemoveFileVariantInput(media_id=movie_id, file_path=body.file_path),
    )


@router.put("/{movie_id}/files/primary")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def set_primary_file(
    movie_id: str,
    body: SetPrimaryFileRequest,
    use_case: SetPrimaryFileUseCase = Depends(
        Provide[ApplicationContainer.media.set_primary_file],
    ),
) -> dict[str, Any]:
    """Set a file variant as primary."""
    result = await use_case.execute(
        SetPrimaryFileInput(media_id=movie_id, file_path=body.file_path),
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
