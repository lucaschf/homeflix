"""Admin REST API routes for the TMDB relink workflow.

Three endpoints, all gated by ``current_admin_user``:

* ``GET  /admin/movies/needs-review`` — listing of movies whose
  enrichment couldn't find a TMDB match.
* ``GET  /admin/movies/{id}/tmdb-suggestions`` — live TMDB picker
  payload (movie + TV candidates) seeded by the movie's title/year.
* ``POST /admin/movies/{id}/relink`` — admin commits a pick. Movie
  picks refresh the enrichment in place; TV picks 422 with a
  pointer to the deferred promote-to-series flow.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.application.dtos.admin_relink_dtos import (
    GetMovieTmdbSuggestionsInput,
    RelinkMovieInput,
)
from src.modules.media.application.use_cases.get_movie_tmdb_suggestions import (
    GetMovieTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.list_movies_needing_review import (
    ListMoviesNeedingReviewUseCase,
)
from src.modules.media.application.use_cases.relink_movie import RelinkMovieUseCase
from src.modules.media.presentation.schemas import RelinkMovieRequest

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Movie Relink"])


@router.get("/movies/needs-review")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_movies_needing_review(
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListMoviesNeedingReviewUseCase = Depends(
        Provide[ApplicationContainer.media.list_movies_needing_review],
    ),
) -> dict[str, Any]:
    """List movies whose enrichment couldn't resolve a TMDB match."""
    output = await use_case.execute()
    return api_list([asdict(m) for m in output.movies])


@router.get("/movies/{movie_id}/tmdb-suggestions")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_movie_tmdb_suggestions(
    movie_id: str,
    _admin: UserModel = Depends(current_admin_user),
    use_case: GetMovieTmdbSuggestionsUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_tmdb_suggestions],
    ),
) -> dict[str, Any]:
    """Return TMDB movie + TV candidates seeded by the movie's title/year."""
    output = await use_case.execute(GetMovieTmdbSuggestionsInput(movie_id=movie_id))
    return api_single("tmdb_suggestions", asdict(output))


@router.post("/movies/{movie_id}/relink")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def relink_movie(
    movie_id: str,
    body: RelinkMovieRequest,
    _admin: UserModel = Depends(current_admin_user),
    use_case: RelinkMovieUseCase = Depends(
        Provide[ApplicationContainer.media.relink_movie],
    ),
) -> dict[str, Any]:
    """Stamp the picked TMDB id on the movie and force-enrich."""
    output = await use_case.execute(
        RelinkMovieInput(
            movie_id=movie_id,
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
        ),
    )
    return api_single("relink", asdict(output))


__all__ = ["router"]
