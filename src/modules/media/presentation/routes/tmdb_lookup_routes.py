"""Catalog lookup endpoint that powers the "Request a title" dialog.

A thin authenticated proxy in front of the external metadata
provider (today: TMDB) so the provider key stays server-side and
the public URL doesn't leak which adapter is in use. The dialog
calls this with whatever the user pasted — TMDB id, IMDb id, TMDB
/ IMDb URL, or plain title — and gets back a list of picker
candidates with title, year, overview, poster. The user picks one
card and the frontend POSTs the chosen ``(tmdb_id, media_type)``
to ``/catalog-requests``.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_user
from src.modules.media.application.dtos.tmdb_lookup_dtos import SearchTmdbTitlesInput
from src.modules.media.application.use_cases.search_tmdb_titles import (
    SearchTmdbTitlesUseCase,
)

_MIN_LIMIT = 1
_MAX_LIMIT = 10
_DEFAULT_LIMIT = 5
_MAX_QUERY_LEN = 500

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog Lookup"])


@router.get("/lookup")
@inject
async def lookup_catalog_title(
    q: str = Query(..., min_length=1, max_length=_MAX_QUERY_LEN),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=_MIN_LIMIT, le=_MAX_LIMIT),
    _user: AuthenticatedUser = Depends(authenticated_user),
    use_case: SearchTmdbTitlesUseCase = Depends(
        Provide[ApplicationContainer.media.search_tmdb_titles],
    ),
) -> dict[str, Any]:
    """Resolve ``q`` into picker candidates for the request dialog.

    ``q`` accepts five shapes; the parser routes each to the cheapest
    provider call:

    - TMDB URL → one ``/movie/{id}`` or ``/tv/{id}`` fetch
    - IMDb URL or bare ``ttXXXXXXX`` → one ``/find/{id}`` fetch
    - bare numeric → both ``/movie/{id}`` + ``/tv/{id}`` in parallel
    - anything else → ``/search/movie`` + ``/search/tv`` in parallel,
      ``limit`` each

    Returns at most two candidates on the by-id branches and at most
    ``2 * limit`` on the free-text branch. Movies appear before
    series so a paste from a film URL renders the expected card
    first; the UI can re-sort if it prefers.
    """
    output = await use_case.execute(SearchTmdbTitlesInput(query=q, limit=limit))
    return api_single("catalog_lookup", asdict(output))


__all__ = ["router"]
