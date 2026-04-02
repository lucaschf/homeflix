"""Media use cases (re-export for backwards compatibility)."""

from src.modules.media.application.use_cases import (
    GetMovieByIdUseCase,
    GetSeriesByIdUseCase,
    ListMoviesUseCase,
    ListSeriesUseCase,
)

__all__ = [
    "GetMovieByIdUseCase",
    "GetSeriesByIdUseCase",
    "ListMoviesUseCase",
    "ListSeriesUseCase",
]
