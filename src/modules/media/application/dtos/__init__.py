"""Media DTOs for application layer."""

from src.modules.media.application.dtos.movie_dtos import (
    GetMovieByIdInput,
    ListMoviesInput,
    ListMoviesOutput,
    MovieOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.dtos.series_dtos import (
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
