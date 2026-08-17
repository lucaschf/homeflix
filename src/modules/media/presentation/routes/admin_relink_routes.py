"""Admin REST API routes for the TMDB relink / enrichment-review workflow.

All endpoints are gated by ``authenticated_admin``. Movies:

* ``GET  /admin/movies/needs-review`` — listing of movies whose
  enrichment couldn't find a TMDB match (or were flagged as wrong).
* ``POST /admin/movies/{id}/flag-enrichment`` — flag an enriched movie
  whose metadata matched the wrong title.
* ``GET  /admin/movies/{id}/tmdb-suggestions`` — live TMDB picker
  payload (movie + TV candidates) seeded by the movie's title/year.
* ``POST /admin/movies/{id}/relink`` — admin commits a pick. Movie
  picks refresh the enrichment in place; TV picks 422 with a
  pointer to the deferred promote-to-series flow.

Series (full review + relink workflow):

* ``GET  /admin/series/needs-review`` — listing of series needing review.
* ``POST /admin/series/{id}/flag-enrichment`` — flag a wrongly-enriched
  series.
* ``GET  /admin/series/{id}/tmdb-suggestions`` — live TMDB picker
  (TV candidates) seeded by the series' title/start year.
* ``POST /admin/series/{id}/relink`` — admin commits a TV pick; the
  series is re-pointed at the chosen TMDB id and force-enriched.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.admin_relink_dtos import (
    FlagMovieEnrichmentReviewInput,
    FlagSeriesEnrichmentReviewInput,
    GetMovieTmdbSuggestionsInput,
    GetSeriesTmdbSuggestionsInput,
    PromoteMovieToSeriesInput,
    RelinkMovieInput,
    RelinkSeriesInput,
)
from src.modules.media.application.use_cases.flag_movie_enrichment_review import (
    FlagMovieEnrichmentReviewUseCase,
)
from src.modules.media.application.use_cases.flag_series_enrichment_review import (
    FlagSeriesEnrichmentReviewUseCase,
)
from src.modules.media.application.use_cases.get_movie_tmdb_suggestions import (
    GetMovieTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.get_series_tmdb_suggestions import (
    GetSeriesTmdbSuggestionsUseCase,
)
from src.modules.media.application.use_cases.list_movies_needing_review import (
    ListMoviesNeedingReviewUseCase,
)
from src.modules.media.application.use_cases.list_series_needing_review import (
    ListSeriesNeedingReviewUseCase,
)
from src.modules.media.application.use_cases.promote_movie_to_series import (
    PromoteMovieToSeriesUseCase,
)
from src.modules.media.application.use_cases.relink_movie import RelinkMovieUseCase
from src.modules.media.application.use_cases.relink_series import RelinkSeriesUseCase
from src.modules.media.presentation.schemas import (
    PromoteMovieToSeriesRequest,
    RelinkMovieRequest,
    RelinkSeriesRequest,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Movie Relink"])


@router.get("/movies/needs-review")
@inject
async def list_movies_needing_review(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListMoviesNeedingReviewUseCase = Depends(
        Provide[ApplicationContainer.media.list_movies_needing_review],
    ),
) -> dict[str, Any]:
    """List movies whose enrichment couldn't resolve a TMDB match."""
    output = await use_case.execute()
    return api_list([asdict(m) for m in output.movies])


@router.post("/movies/{movie_id}/flag-enrichment")
@inject
async def flag_movie_enrichment(
    movie_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: FlagMovieEnrichmentReviewUseCase = Depends(
        Provide[ApplicationContainer.media.flag_movie_enrichment_review],
    ),
) -> dict[str, Any]:
    """Flag a wrongly-enriched movie so it re-enters the review queue."""
    output = await use_case.execute(FlagMovieEnrichmentReviewInput(movie_id=movie_id))
    return api_single("flag_enrichment", asdict(output))


@router.get("/movies/{movie_id}/tmdb-suggestions")
@inject
async def get_movie_tmdb_suggestions(
    movie_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetMovieTmdbSuggestionsUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_tmdb_suggestions],
    ),
) -> dict[str, Any]:
    """Return TMDB movie + TV candidates seeded by the movie's title/year."""
    output = await use_case.execute(GetMovieTmdbSuggestionsInput(movie_id=movie_id))
    return api_single("tmdb_suggestions", asdict(output))


@router.post("/movies/{movie_id}/relink")
@inject
async def relink_movie(
    movie_id: str,
    body: RelinkMovieRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
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


@router.post("/movies/{movie_id}/promote-to-series")
@inject
async def promote_movie_to_series(
    movie_id: str,
    body: PromoteMovieToSeriesRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: PromoteMovieToSeriesUseCase = Depends(
        Provide[ApplicationContainer.media.promote_movie_to_series],
    ),
) -> dict[str, Any]:
    """Convert a misclassified movie into a series using a TMDB tv id."""
    output = await use_case.execute(
        PromoteMovieToSeriesInput(movie_id=movie_id, tmdb_id=body.tmdb_id),
    )
    return api_single("promote_to_series", asdict(output))


@router.get("/series/needs-review")
@inject
async def list_series_needing_review(
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListSeriesNeedingReviewUseCase = Depends(
        Provide[ApplicationContainer.media.list_series_needing_review],
    ),
) -> dict[str, Any]:
    """List series needing enrichment review (failed match or flagged)."""
    output = await use_case.execute()
    return api_list([asdict(s) for s in output.series])


@router.post("/series/{series_id}/flag-enrichment")
@inject
async def flag_series_enrichment(
    series_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: FlagSeriesEnrichmentReviewUseCase = Depends(
        Provide[ApplicationContainer.media.flag_series_enrichment_review],
    ),
) -> dict[str, Any]:
    """Flag a wrongly-enriched series so it re-enters the review queue."""
    output = await use_case.execute(FlagSeriesEnrichmentReviewInput(series_id=series_id))
    return api_single("flag_enrichment", asdict(output))


@router.get("/series/{series_id}/tmdb-suggestions")
@inject
async def get_series_tmdb_suggestions(
    series_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetSeriesTmdbSuggestionsUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_tmdb_suggestions],
    ),
) -> dict[str, Any]:
    """Return TMDB TV candidates seeded by the series' title/start year."""
    output = await use_case.execute(GetSeriesTmdbSuggestionsInput(series_id=series_id))
    return api_single("tmdb_suggestions", asdict(output))


@router.post("/series/{series_id}/relink")
@inject
async def relink_series(
    series_id: str,
    body: RelinkSeriesRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: RelinkSeriesUseCase = Depends(
        Provide[ApplicationContainer.media.relink_series],
    ),
) -> dict[str, Any]:
    """Stamp the picked TMDB id on the series and force-enrich."""
    output = await use_case.execute(
        RelinkSeriesInput(
            series_id=series_id,
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
        ),
    )
    return api_single("relink", asdict(output))


__all__ = ["router"]
