"""Movie DTOs (re-export for backwards compatibility)."""
from src.modules.media.application.dtos.movie_dtos import (
    GetMovieByIdInput,
    ListMoviesInput,
    ListMoviesOutput,
    MovieOutput,
    MovieSummaryOutput,
)

__all__ = [
    "GetMovieByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
]
