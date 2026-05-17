"""DTOs for the admin enrichment-review and TMDB relink endpoints.

Shared by:
    - ListMoviesNeedingReviewUseCase
    - GetMovieTmdbSuggestionsUseCase
    - RelinkMovieUseCase

These shapes mirror what the admin UI consumes — slim per-row data
for the listing, structured TMDB cards for the picker, and a single
relink command payload.
"""

from dataclasses import dataclass, field
from typing import Literal

MediaType = Literal["movie", "tv"]


@dataclass(frozen=True)
class NeedsReviewMovieOutput:
    """One row on the admin "needs review" list.

    Intentionally slim — the movie isn't enriched yet, so fields the
    catalog card would normally show (poster, synopsis, genres) are
    NULL. The admin needs just enough to identify the file and pick
    a TMDB match.

    Attributes:
        id: External movie id (``mov_xxx``).
        title: Title as the scanner extracted it from the folder.
        year: Year as the scanner extracted it from the folder.
        file_path: Primary file path on disk, or ``None`` if no
            variant has been registered yet.
    """

    id: str
    title: str
    year: int
    file_path: str | None


@dataclass(frozen=True)
class ListMoviesNeedingReviewOutput:
    """Top-level response for the needs-review listing."""

    movies: list[NeedsReviewMovieOutput] = field(default_factory=list)


@dataclass(frozen=True)
class TmdbSuggestionOutput:
    """A single TMDB suggestion card shown in the relink picker.

    Both movie and TV candidates share this shape — the
    ``media_type`` field tells the front which TMDB endpoint
    produced it and which relink ``media_type`` to send back.

    Attributes:
        tmdb_id: TMDB primary key for the entry.
        media_type: ``"movie"`` (from ``/search/movie``) or ``"tv"``
            (from ``/search/tv``).
        title: Display title from TMDB.
        year: Release / first-air year, or ``None`` if TMDB has no
            usable date for this entry.
        overview: Synopsis (may be empty for obscure entries).
        poster_url: Absolute TMDB poster URL, or ``None`` when no
            poster is on file.
    """

    tmdb_id: int
    media_type: MediaType
    title: str
    year: int | None
    overview: str | None
    poster_url: str | None


@dataclass(frozen=True)
class GetMovieTmdbSuggestionsInput:
    """Input for the suggestion picker.

    Attributes:
        movie_id: External movie id whose folder title + year are
            the search seed.
    """

    movie_id: str


@dataclass(frozen=True)
class GetMovieTmdbSuggestionsOutput:
    """Picker payload — movie and TV candidates rendered side by side."""

    movie_id: str
    movies: list[TmdbSuggestionOutput] = field(default_factory=list)
    series: list[TmdbSuggestionOutput] = field(default_factory=list)


@dataclass(frozen=True)
class RelinkMovieInput:
    """Admin's pick from the suggestion picker.

    Attributes:
        movie_id: External movie id to relink.
        tmdb_id: TMDB id the admin selected.
        media_type: ``"movie"`` triggers an enrichment refresh against
            the picked id. ``"tv"`` is rejected by this PR with a
            "use promote-to-series" error — the cross-BC conversion
            lives in a follow-up.
    """

    movie_id: str
    tmdb_id: int
    media_type: MediaType


@dataclass(frozen=True)
class RelinkMovieOutput:
    """Result of a relink command.

    Attributes:
        movie_id: External movie id (echoed).
        enriched: ``True`` when the new TMDB metadata was written.
        provider: Provider that resolved the new metadata
            (``"tmdb"`` in practice).
        error: Failure reason when ``enriched`` is ``False`` (e.g.
            TMDB id couldn't be fetched, or media_type isn't
            supported yet).
    """

    movie_id: str
    enriched: bool
    provider: str | None = None
    error: str | None = None


__all__ = [
    "GetMovieTmdbSuggestionsInput",
    "GetMovieTmdbSuggestionsOutput",
    "ListMoviesNeedingReviewOutput",
    "MediaType",
    "NeedsReviewMovieOutput",
    "RelinkMovieInput",
    "RelinkMovieOutput",
    "TmdbSuggestionOutput",
]
