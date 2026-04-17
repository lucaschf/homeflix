"""Catalog search REST API route."""

from dataclasses import asdict
from typing import Any, Literal

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.application.pagination import MAX_PAGE_SIZE
from src.building_blocks.presentation import api_list
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.search_dtos import SearchInput
from src.modules.media.application.use_cases.search_catalog import SearchCatalogUseCase

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.get("/search")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def search(
    q: str = Query(..., min_length=1, description="Full-text search query"),
    type: Literal["movie", "series"] | None = Query(
        default=None,
        description="Restrict to a single media type",
    ),
    genre: str | None = Query(default=None, description="Canonical genre id filter"),
    year_min: int | None = Query(default=None, description="Inclusive lower bound on year"),
    year_max: int | None = Query(default=None, description="Inclusive upper bound on year"),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE, description="Max results"),
    lang: str = "en",
    use_case: SearchCatalogUseCase = Depends(
        Provide[ApplicationContainer.media.search_catalog],
    ),
) -> dict[str, Any]:
    """Full-text search across movies and series.

    Searches title, original_title, synopsis, cast (movies), and
    genres via FTS5. Results are ranked by relevance (best matches
    first). Optional filters narrow the result set at the SQL level.

    Query params:
        q: Search string. Prefix matching is automatic (``"incep"``
            matches ``"Inception"``).
        type: ``"movie"`` or ``"series"`` — omit to search both.
        genre: Canonical genre id (exact match).
        year_min / year_max: Release year range (inclusive).
        limit: Page size, clamped to ``[1, MAX_PAGE_SIZE]``.
        lang: Language for localized titles/synopses/genres.
    """
    result = await use_case.execute(
        SearchInput(
            query=q,
            media_type=type,
            genre=genre,
            year_min=year_min,
            year_max=year_max,
            lang=lang,
            limit=limit,
        )
    )
    return api_list(
        [asdict(item) for item in result.items],
        metadata_extras={"total": result.total},
    )


__all__ = ["router"]
