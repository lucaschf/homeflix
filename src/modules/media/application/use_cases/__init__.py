"""Media use cases."""

from src.modules.media.application.use_cases.add_file_variant import AddFileVariantUseCase
from src.modules.media.application.use_cases.delete_movie import DeleteMovieUseCase
from src.modules.media.application.use_cases.get_file_variants import GetFileVariantsUseCase
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.list_movies import ListMoviesUseCase
from src.modules.media.application.use_cases.list_series import ListSeriesUseCase
from src.modules.media.application.use_cases.remove_file_variant import RemoveFileVariantUseCase
from src.modules.media.application.use_cases.set_primary_file import SetPrimaryFileUseCase

__all__ = [
    "AddFileVariantUseCase",
    "DeleteMovieUseCase",
    "GetFileVariantsUseCase",
    "GetMovieByIdUseCase",
    "GetSeriesByIdUseCase",
    "ListMoviesUseCase",
    "ListSeriesUseCase",
    "RemoveFileVariantUseCase",
    "SetPrimaryFileUseCase",
]
