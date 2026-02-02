"""Media DTOs for application layer."""

from src.application.media.dtos.movie_dtos import (
    GetMovieByIdInput,
    ListMoviesInput,
    ListMoviesOutput,
    MovieOutput,
    MovieSummaryOutput,
)
from src.application.media.dtos.series_dtos import (
    EpisodeOutput,
    GetSeriesByIdInput,
    ListSeriesInput,
    ListSeriesOutput,
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
