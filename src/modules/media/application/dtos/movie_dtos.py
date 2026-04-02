"""Movie DTOs for application layer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GetMovieByIdInput:
    """Input for GetMovieByIdUseCase.

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
    file_path: str | None
    file_size: int | None
    resolution: str | None
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
    poster_path: str | None
    resolution: str | None
    genres: list[str]


@dataclass(frozen=True)
class ListMoviesInput:
    """Input for ListMoviesUseCase.

    Attributes:
        limit: Maximum number of movies to return (optional, default: all).
    """

    limit: int | None = None


@dataclass(frozen=True)
class ListMoviesOutput:
    """Output for ListMoviesUseCase.

    Attributes:
        movies: List of movie summaries.
        total_count: Total number of movies in the library.
    """

    movies: list[MovieSummaryOutput]
    total_count: int


__all__ = [
    "GetMovieByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
]
