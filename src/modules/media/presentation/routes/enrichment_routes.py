"""Metadata enrichment REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.enrichment_dtos import (
    BulkEnrichInput,
    EnrichMediaInput,
)
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.presentation.schemas import (
    BulkEnrichResponse,
    EnrichRequest,
    EnrichResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Metadata Enrichment"])


@router.post(  # type: ignore[misc]
    "/movies/{movie_id}/enrich",
    response_model=EnrichResponse,
)
@inject  # type: ignore[misc]
async def enrich_movie(
    movie_id: str,
    body: EnrichRequest | None = None,
    use_case: EnrichMovieMetadataUseCase = Depends(
        Provide[ApplicationContainer.media.enrich_movie_metadata],
    ),
) -> dict[str, Any]:
    """Enrich a movie with metadata from TMDB."""
    force = body.force if body else False
    output = await use_case.execute(EnrichMediaInput(media_id=movie_id, force=force))
    return asdict(output)


@router.post(  # type: ignore[misc]
    "/series/{series_id}/enrich",
    response_model=EnrichResponse,
)
@inject  # type: ignore[misc]
async def enrich_series(
    series_id: str,
    body: EnrichRequest | None = None,
    use_case: EnrichSeriesMetadataUseCase = Depends(
        Provide[ApplicationContainer.media.enrich_series_metadata],
    ),
) -> dict[str, Any]:
    """Enrich a series with metadata from TMDB."""
    force = body.force if body else False
    output = await use_case.execute(EnrichMediaInput(media_id=series_id, force=force))
    return asdict(output)


@router.post(  # type: ignore[misc]
    "/enrich",
    response_model=BulkEnrichResponse,
)
@inject  # type: ignore[misc]
async def bulk_enrich(
    body: EnrichRequest | None = None,
    use_case: BulkEnrichMetadataUseCase = Depends(
        Provide[ApplicationContainer.media.bulk_enrich_metadata],
    ),
) -> dict[str, Any]:
    """Enrich all movies and series with metadata from TMDB."""
    force = body.force if body else False
    output = await use_case.execute(BulkEnrichInput(force=force))
    return asdict(output)


__all__ = ["router"]
