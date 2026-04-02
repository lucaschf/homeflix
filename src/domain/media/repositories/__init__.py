"""Media domain repository interfaces (re-export for backwards compatibility)."""

from src.modules.media.domain.repositories import MovieRepository, SeriesRepository

__all__ = [
    "MovieRepository",
    "SeriesRepository",
]
