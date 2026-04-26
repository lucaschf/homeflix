"""People (cast bio) REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.media.application.use_cases.get_person_bio import (
    GetPersonBioInput,
    GetPersonBioUseCase,
)

router = APIRouter(prefix="/api/v1/people", tags=["People"])


@router.get("/{tmdb_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_person(
    tmdb_id: int,
    lang: str = "en-US",
    use_case: GetPersonBioUseCase = Depends(
        Provide[ApplicationContainer.media.get_person_bio],
    ),
) -> dict[str, Any]:
    """Fetch biographical metadata for a TMDB person.

    Used by the actor page to render bio + birth date + known
    department alongside the catalog filmography. The ``tmdb_id``
    path param is captured during movie enrichment and forwarded by
    the cast card via ``location.state``.

    Query params:
        lang: BCP-47 language tag (default ``en-US``). When the
            requested language has no biography on TMDB the use case
            falls back to English bio while keeping the rest of the
            payload localized.

    Returns 404 when the provider has no record for the id (deleted
    person, propagated 404, network error). The actor page degrades
    gracefully on 404 and keeps a name-only header.
    """
    result = await use_case.execute(GetPersonBioInput(tmdb_id=tmdb_id, lang=lang))
    if result is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return api_single("person", asdict(result))


__all__ = ["router"]
