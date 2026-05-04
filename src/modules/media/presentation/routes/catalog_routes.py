"""Catalog (cross-cutting movies + series) REST API routes."""

from dataclasses import asdict
from typing import Any, Literal

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.building_blocks.presentation import Pagination, api_list
from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.catalog_dtos import (
    ListByGenreInput,
    ListGenresInput,
    ListRecentlyAddedCatalogInput,
    MediaTypeFilter,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.application.use_cases.list_movies_by_actor import (
    ListMoviesByActorInput,
    ListMoviesByActorUseCase,
)
from src.modules.media.application.use_cases.list_recently_added_catalog import (
    ListRecentlyAddedCatalogUseCase,
)
from src.modules.media.presentation.dependencies import resolve_profile_id

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog"])

# Shared OpenAPI/validation config for the `?type=` query param. Kept
# as a module-level constant so both routes stay identical and changes
# to the description show up in a single place.
_MEDIA_TYPE_QUERY: MediaTypeFilter | None = Query(
    default=None,
    description=(
        "Optional filter — restrict the result to a single media type. "
        "Accepts 'movie' or 'series'; omit to aggregate both."
    ),
)


@router.get("/genres")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_genres(
    lang: str = "en",
    type: Literal["movie", "series"] | None = _MEDIA_TYPE_QUERY,
    profile_id: str = Depends(resolve_profile_id),
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

    Query params:
        lang: Language code for localized genre names.
        type: Optional ``"movie"`` or ``"series"`` filter. When set,
            counts only reflect the matching media type so the Movies
            and Series tabs can skip genres that exist only on the
            other side.
    """
    result = await use_case.execute(
        ListGenresInput(profile_id=profile_id, lang=lang, media_type=type)
    )
    return api_list([asdict(g) for g in result.genres])


@router.get("/by-genre/{genre}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_by_genre(
    genre: str,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    lang: str = "en",
    type: Literal["movie", "series"] | None = _MEDIA_TYPE_QUERY,
    profile_id: str = Depends(resolve_profile_id),
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
        type: Optional ``"movie"`` or ``"series"`` filter. When set,
            only the matching stream is queried so the Movies and
            Series tabs can show a genre restricted to their side of
            the catalog without mixing in the other.
    """
    clamped_limit = max(1, min(limit, MAX_PAGE_SIZE))
    result = await use_case.execute(
        ListByGenreInput(
            profile_id=profile_id,
            genre=genre,
            cursor=cursor,
            limit=clamped_limit,
            lang=lang,
            media_type=type,
        )
    )
    return api_list(
        [asdict(item) for item in result.items],
        pagination=Pagination(has_more=result.has_more, next_cursor=result.next_cursor),
    )


@router.get("/recently-added")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_recently_added_catalog(
    limit: int = 20,
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: ListRecentlyAddedCatalogUseCase = Depends(
        Provide[ApplicationContainer.media.list_recently_added_catalog],
    ),
) -> dict[str, Any]:
    """Mixed top-N most recently added titles across movies + series.

    Each repo is queried for its top ``limit`` newest entries (ordered
    by ``id DESC``); the two streams are merged in Python by
    ``created_at`` descending and trimmed to ``limit``. ``limit`` is
    clamped to ``[1, 50]`` so the home carousel can't pull the full
    catalog.

    Query params:
        limit: Maximum items returned. Defaults to 20.
        lang: Language code for localized titles, synopses, and genre
            names returned in each item.
    """
    clamped_limit = max(1, min(limit, 50))
    result = await use_case.execute(
        ListRecentlyAddedCatalogInput(profile_id=profile_id, limit=clamped_limit, lang=lang),
    )
    return api_list([asdict(item) for item in result.items])


@router.get("/by-actor")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_by_actor(
    name: str,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: ListMoviesByActorUseCase = Depends(
        Provide[ApplicationContainer.media.list_movies_by_actor],
    ),
) -> dict[str, Any]:
    """Paginated listing of movies whose cast contains ``name``.

    Match is by exact display name. The local catalog has no actor
    id (TMDB person ids aren't persisted yet), so the route takes a
    name in the query string and resolves it server-side. Two real
    people who share a display name would collide — acceptable for a
    personal-library scale catalog and reversible without breaking
    the URL once a TMDB person id is persisted.

    Series cast isn't part of the domain yet, so this route is
    movies-only. When series cast lands, the use case can be
    promoted to a dual-stream merge (mirroring ``ListByGenreUseCase``)
    and the response shape will gain a ``type`` discriminator
    without changing the URL.

    Query params:
        name: Exact display name of the cast member (e.g.,
            ``Sigourney Weaver``). Required.
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
        ListMoviesByActorInput(
            profile_id=profile_id,
            actor_name=name,
            cursor=cursor,
            limit=clamped_limit,
            lang=lang,
        )
    )
    return api_list(
        [asdict(movie) for movie in result.movies],
        pagination=Pagination(has_more=result.has_more, next_cursor=result.next_cursor),
    )


__all__ = ["router"]
