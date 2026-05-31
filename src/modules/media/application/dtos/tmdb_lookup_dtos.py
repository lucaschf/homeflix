"""DTOs for the TMDB lookup endpoint that powers the request dialog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LookupMediaType = Literal["movie", "tv"]


@dataclass(frozen=True)
class SearchTmdbTitlesInput:
    """Input for the catalog-request lookup use case.

    Attributes:
        query: Free-form text from the dialog input. Accepts a bare
            TMDB id (``603``), an IMDb id (``tt0133093``), a TMDB
            URL (``https://www.themoviedb.org/movie/603``), an IMDb
            URL (``https://www.imdb.com/title/tt0133093/``) or a
            plain title. The use case parses the shape internally.
        limit: Maximum candidates per kind on the free-text search
            branch (movie + tv each return up to ``limit``). Ignored
            on the by-id branches — those return at most one match
            per kind. Caller (route) clamps to a sensible range.
    """

    query: str
    limit: int = 5


@dataclass(frozen=True)
class TmdbLookupCandidate:
    """One row in the request-dialog picker.

    Attributes:
        tmdb_id: TMDB primary key.
        media_type: ``"movie"`` (``/movie/{id}``) or ``"tv"`` (``/tv/{id}``).
        title: Display title from TMDB.
        year: Release / first-air year, or ``None`` when the source
            lacks a usable date.
        overview: Synopsis (possibly empty).
        poster_url: Absolute poster URL, or ``None``.
    """

    tmdb_id: int
    media_type: LookupMediaType
    title: str
    year: int | None
    overview: str | None
    poster_url: str | None


@dataclass(frozen=True)
class SearchTmdbTitlesOutput:
    """Response shape returned to the request dialog.

    Attributes:
        query: Echo of the cleaned input. Lets the UI tell the
            user what was actually searched after stripping.
        kind: Which detection branch ran — ``"tmdb_id"`` /
            ``"imdb_id"`` / ``"text"``. Useful for analytics +
            for the UI to render a hint ("Matched by TMDB id …").
        candidates: Picker rows, movies first, then series.
    """

    query: str
    kind: Literal["tmdb_id", "imdb_id", "text"]
    candidates: list[TmdbLookupCandidate] = field(default_factory=list)


__all__ = [
    "LookupMediaType",
    "SearchTmdbTitlesInput",
    "SearchTmdbTitlesOutput",
    "TmdbLookupCandidate",
]
