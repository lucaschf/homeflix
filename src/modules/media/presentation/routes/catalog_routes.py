"""Catalog (cross-cutting movies + series) REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.catalog_dtos import (
    ListByGenreInput,
    ListGenresInput,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog"])


@router.get("/genres")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_genres(
    lang: str = "en",
    use_case: ListGenresUseCase = Depends(
        Provide[ApplicationContainer.media.list_genres],
    ),
) -> dict[str, Any]:
    """List every genre present in the library, with counts and localized names.

    Single non-paginated request — returns the full set so the
    frontend can build the carousel layout in one shot. Each entry
    has the canonical English ``id`` (used as the filter key for
    ``GET /api/v1/catalog/by-genre/{id}``) and the localized ``name``
    for display.

    Sorted by count descending, then alphabetically by display name —
    most-populated carousels surface first on the Home page.
    """
    result = await use_case.execute(ListGenresInput(lang=lang))
    return {
        "type": "list",
        "data": [asdict(g) for g in result.genres],
    }


@router.get("/by-genre/{genre}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_by_genre(
    genre: str,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    lang: str = "en",
    use_case: ListByGenreUseCase = Depends(
        Provide[ApplicationContainer.media.list_by_genre],
    ),
) -> dict[str, Any]:
    """Paginated mixed listing of movies + series for a single genre.

    The ``genre`` path parameter is the canonical English id from
    ``GET /api/v1/catalog/genres``. Items are merged from both media
    types, sorted alphabetically by title, and paginated with an
    opaque dual-stream cursor.

    Query params:
        cursor: Opaque token returned by the previous page's
            ``metadata.pagination.next_cursor``. Omit on the first
            request. Invalid / tampered cursors silently start over
            from the beginning.
        limit: Page size, clamped to ``[1, MAX_PAGE_SIZE]``.
        lang: Language code for localized titles, synopses, and
            genre names returned in each item.
    """
    clamped_limit = max(1, min(limit, MAX_PAGE_SIZE))
    result = await use_case.execute(
        ListByGenreInput(
            genre=genre,
            cursor=cursor,
            limit=clamped_limit,
            lang=lang,
        )
    )
    return {
        "type": "list",
        "data": [asdict(item) for item in result.items],
        "metadata": {
            "pagination": {
                "next_cursor": result.next_cursor,
                "has_more": result.has_more,
            },
        },
    }


__all__ = ["router"]
