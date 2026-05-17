"""Pydantic schemas for the admin TMDB relink endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class RelinkMovieRequest(BaseModel):
    """Request body for ``POST /admin/movies/{id}/relink``.

    The admin picked one of the cards returned by
    ``GET /admin/movies/{id}/tmdb-suggestions`` and is committing
    that choice. ``media_type`` mirrors which TMDB endpoint produced
    the card so the server knows whether to refresh the movie
    in-place (``movie``) or short-circuit to the not-yet-implemented
    promote-to-series flow (``tv``).
    """

    tmdb_id: int = Field(..., ge=1, description="TMDB primary key of the picked entry.")
    media_type: Literal["movie", "tv"] = Field(
        ...,
        description=(
            "Which TMDB endpoint the picked card came from. 'movie' "
            "triggers an enrichment refresh; 'tv' returns a 422 "
            "asking to use the future promote-to-series endpoint."
        ),
    )


__all__ = ["RelinkMovieRequest"]
