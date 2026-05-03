"""Media DTOs for application layer."""

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
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
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
    MovieOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.dtos.series_dtos import (
    EpisodeOutput,
    GetSeriesByIdInput,
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
    ListSeriesInput,
    ListSeriesOutput,
    SeasonOutput,
    SeriesOutput,
    SeriesSummaryOutput,
)

__all__ = [
    # Featured DTOs
    "FeaturedItemOutput",
    "GetFeaturedInput",
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
    "ListRecentlyAddedMoviesInput",
    "ListRecentlyAddedMoviesOutput",
    "MovieOutput",
    "MovieSummaryOutput",
    # Series DTOs
    "EpisodeOutput",
    "GetSeriesByIdInput",
    "ListRecentlyAddedSeriesInput",
    "ListRecentlyAddedSeriesOutput",
    "ListSeriesInput",
    "ListSeriesOutput",
    "SeasonOutput",
    "SeriesOutput",
    "SeriesSummaryOutput",
]
