"""TMDB collection (franchise) detail REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.collection_dtos import (
    GetCollectionByTmdbIdInput,
)
from src.modules.media.application.use_cases.get_collection_by_tmdb_id import (
    GetCollectionByTmdbIdUseCase,
)
from src.modules.media.presentation.dependencies import resolve_profile_id

router = APIRouter(prefix="/api/v1/collections", tags=["Collections"])


@router.get("/{tmdb_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_collection(
    tmdb_id: int = Path(..., ge=1, description="TMDB collection id."),
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetCollectionByTmdbIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_collection_by_tmdb_id],
    ),
) -> dict[str, Any]:
    """Return the Collection Detail payload for a TMDB collection id.

    Aggregates TMDB franchise metadata, the local catalog, and any
    catalog-request state into a single shape the
    ``/collection/:tmdbId`` page can render in one round-trip.

    Returns 404 when TMDB has no record for ``tmdb_id`` or the
    upstream call fails — see ``GetCollectionByTmdbIdUseCase``.
    """
    result = await use_case.execute(
        GetCollectionByTmdbIdInput(profile_id=profile_id, tmdb_id=tmdb_id, lang=lang),
    )
    return api_single("collection", asdict(result))


__all__ = ["router"]
