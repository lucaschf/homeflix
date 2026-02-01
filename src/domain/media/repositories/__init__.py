"""Media domain repository interfaces."""

from src.domain.media.repositories.movie_repository import MovieRepository
from src.domain.media.repositories.series_repository import SeriesRepository

__all__ = [
    "MovieRepository",
    "SeriesRepository",
]
