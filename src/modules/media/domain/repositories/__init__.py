"""Media domain repository interfaces."""

from src.modules.media.domain.repositories.movie_repository import MovieRepository
from src.modules.media.domain.repositories.series_repository import SeriesRepository

__all__ = [
    "MovieRepository",
    "SeriesRepository",
]
