"""Media application layer (re-export for backwards compatibility)."""

from src.modules.media.application.dtos import (
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
from src.modules.media.application.use_cases import (
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
