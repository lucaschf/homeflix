"""Movie DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.media.application.dtos.media_file_dtos import MediaFileOutput


@dataclass(frozen=True)
class GetMovieByIdInput:
    """Input for GetMovieByIdUseCase.

    Attributes:
        movie_id: External ID of the movie (mov_xxx format).
        lang: Language code for localized metadata (e.g., "en", "pt-BR").
    """

    movie_id: str
    lang: str = "en"


@dataclass(frozen=True)
class DeleteMovieInput:
    """Input for DeleteMovieUseCase.

    Attributes:
        movie_id: External ID of the movie (mov_xxx format).
    """

    movie_id: str


@dataclass(frozen=True)
class MovieOutput:
    """Output representation of a Movie.

    Contains all movie fields serialized for API consumption.
    Value objects are converted to primitive types.

    Attributes:
        id: External movie ID (mov_xxx).
        title: Display title.
        original_title: Original language title (if different).
        year: Release year.
        duration_seconds: Duration in seconds.
        duration_formatted: Duration as HH:MM:SS.
        synopsis: Movie synopsis (optional).
        poster_path: Path to poster image (optional).
        backdrop_path: Path to backdrop image (optional).
        genres: List of genre strings.
        file_path: Path to video file (None if no primary file).
        file_size: File size in bytes (None if no primary file).
        resolution: Video resolution (None if no primary file).
        tmdb_id: TMDB external ID (optional).
        imdb_id: IMDB external ID (optional).
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
    """

    id: str
    title: str
    original_title: str | None
    year: int
    duration_seconds: int
    duration_formatted: str
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    genres: list[str]
    cast: list[str]
    directors: list[str]
    writers: list[str]
    content_rating: str | None
    trailer_url: str | None
    file_path: str | None
    file_size: int | None
    resolution: str | None
    files: list[MediaFileOutput]
    tmdb_id: int | None
    imdb_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MovieSummaryOutput:
    """Summary representation of a Movie for list views.

    Contains essential fields for displaying movies in a grid/list.

    Attributes:
        id: External movie ID.
        title: Display title.
        year: Release year.
        duration_formatted: Duration as HH:MM:SS.
        poster_path: Path to poster image (optional).
        resolution: Video resolution.
        genres: List of genre strings.
    """

    id: str
    title: str
    year: int
    duration_formatted: str
    synopsis: str | None
    poster_path: str | None
    backdrop_path: str | None
    resolution: str | None
    variant_count: int
    available_resolutions: list[str]
    genres: list[str]


@dataclass(frozen=True)
class ListMoviesInput:
    """Input for ListMoviesUseCase.

    Attributes:
        cursor: Opaque pagination cursor from the previous page's
            ``next_cursor``. ``None`` (or any invalid token) starts at
            the first page.
        limit: Page size. Routes clamp this to ``[1, MAX_PAGE_SIZE]``
            before constructing the input.
        include_total: When ``True`` the use case asks the repository
            for an extra ``COUNT(*)`` so ``total_count`` is populated.
            Defaults to ``False`` because computing the total is the
            most expensive part of the query and is rarely needed by
            infinite-scroll consumers.
        lang: Language code for localized metadata.
    """

    cursor: str | None = None
    limit: int = 20
    include_total: bool = False
    lang: str = "en"


@dataclass(frozen=True)
class ListMoviesOutput:
    """Output for ListMoviesUseCase.

    Attributes:
        movies: List of movie summaries on this page.
        next_cursor: Opaque token to pass back as ``cursor`` on the
            next request, or ``None`` when there are no more pages.
        has_more: Convenience flag — equivalent to
            ``next_cursor is not None`` but explicit so clients don't
            have to infer it.
        total_count: Total number of (non-deleted) movies in the
            library, or ``None`` when the caller did not request it
            via ``include_total``.
    """

    movies: list[MovieSummaryOutput]
    next_cursor: str | None
    has_more: bool
    total_count: int | None = None


__all__ = [
    "GetMovieByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
]
