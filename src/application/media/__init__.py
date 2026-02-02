"""Media application layer - use cases and DTOs."""

from src.application.media.dtos import (
    EpisodeOutput,
    GetMovieByIdInput,
    GetSeriesByIdInput,
    ListMoviesInput,
    ListMoviesOutput,
    ListSeriesInput,
    ListSeriesOutput,
    MovieOutput,
    MovieSummaryOutput,
    SeasonOutput,
    SeriesOutput,
    SeriesSummaryOutput,
)
from src.application.media.use_cases import (
    GetMovieByIdUseCase,
    GetSeriesByIdUseCase,
    ListMoviesUseCase,
    ListSeriesUseCase,
)

__all__ = [
    # DTOs
    "EpisodeOutput",
    "GetMovieByIdInput",
    "GetSeriesByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "ListSeriesInput",
    "ListSeriesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
    "SeasonOutput",
    "SeriesOutput",
    "SeriesSummaryOutput",
    # Use Cases
    "GetMovieByIdUseCase",
    "GetSeriesByIdUseCase",
    "ListMoviesUseCase",
    "ListSeriesUseCase",
]
