"""Media DTOs (re-export for backwards compatibility)."""

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

__all__ = [
    # Movie DTOs
    "GetMovieByIdInput",
    "ListMoviesInput",
    "ListMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
    # Series DTOs
    "EpisodeOutput",
    "GetSeriesByIdInput",
    "ListSeriesInput",
    "ListSeriesOutput",
    "SeasonOutput",
    "SeriesOutput",
    "SeriesSummaryOutput",
]
