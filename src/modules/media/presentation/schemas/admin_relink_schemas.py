"""Pydantic schemas for the admin TMDB relink endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class RelinkMovieRequest(BaseModel):
    """Request body for ``POST /admin/movies/{id}/relink``.

    Only movie picks ride this endpoint — series picks must hit
    ``POST /admin/movies/{id}/promote-to-series`` instead, since the
    structural conversion needs cross-BC event fanout that the
    in-place enrichment refresh doesn't do. Pydantic's ``Literal``
    enforces the split: a payload with ``media_type="tv"`` is
    rejected at the schema layer with a 422.
    """

    tmdb_id: int = Field(..., ge=1, description="TMDB primary key of the picked entry.")
    media_type: Literal["movie"] = Field(
        ...,
        description=(
            "Must be 'movie'. Series picks use the dedicated "
            "/admin/movies/{id}/promote-to-series endpoint."
        ),
    )


class RelinkSeriesRequest(BaseModel):
    """Request body for ``POST /admin/series/{id}/relink``.

    Only TV picks ride this endpoint. ``media_type`` is pinned to
    ``"tv"`` by ``Literal`` so a ``"movie"`` payload is rejected at the
    schema layer with a 422 — re-pointing a series at a movie (the
    inverse promotion) is not supported.
    """

    tmdb_id: int = Field(..., ge=1, description="TMDB *series* id of the picked entry.")
    media_type: Literal["tv"] = Field(
        ...,
        description="Must be 'tv'. Series can only relink to other TV entries.",
    )


class PromoteMovieToSeriesRequest(BaseModel):
    """Request body for ``POST /admin/movies/{id}/promote-to-series``.

    Admin picked a TV suggestion in the relink picker. Server fetches
    the TMDB series, builds the ``Series + Season + Episodes`` shape,
    moves the original movie's file variants onto the first episode,
    soft-deletes the movie and fans the change out to the
    watch_progress and collections bounded contexts.
    """

    tmdb_id: int = Field(
        ...,
        ge=1,
        description="TMDB *series* id the admin picked from the TV column.",
    )


__all__ = ["PromoteMovieToSeriesRequest", "RelinkMovieRequest", "RelinkSeriesRequest"]
