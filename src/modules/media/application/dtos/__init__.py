"""Media DTOs for application layer."""

from src.modules.media.application.dtos.media_file_dtos import (
    AddFileVariantInput,
    GetFileVariantsInput,
    MediaFileOutput,
    RemoveFileVariantInput,
    SetPrimaryFileInput,
)
from src.modules.media.application.dtos.movie_dtos import (
    DeleteMovieInput,
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
    # MediaFile DTOs
    "AddFileVariantInput",
    "GetFileVariantsInput",
    "MediaFileOutput",
    "RemoveFileVariantInput",
    "SetPrimaryFileInput",
    # Movie DTOs
    "DeleteMovieInput",
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
