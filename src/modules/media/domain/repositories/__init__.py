"""Media domain repository interfaces."""

from src.modules.media.domain.repositories.media_conflict_repository import (
    MediaConflictRepository,
)
from src.modules.media.domain.repositories.movie_repository import MovieRepository
from src.modules.media.domain.repositories.scan_run_repository import ScanRunRepository
from src.modules.media.domain.repositories.series_repository import SeriesRepository

__all__ = [
    "MediaConflictRepository",
    "MovieRepository",
    "ScanRunRepository",
    "SeriesRepository",
]
