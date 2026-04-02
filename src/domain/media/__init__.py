"""Media Catalog bounded context (re-export for backwards compatibility)."""

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    MediaId,
    MovieId,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
    parse_media_id,
)

__all__ = [
    "Duration",
    "Episode",
    "EpisodeId",
    "FilePath",
    "Genre",
    "MediaId",
    "Movie",
    "MovieId",
    "MovieRepository",
    "Resolution",
    "Season",
    "SeasonId",
    "Series",
    "SeriesId",
    "SeriesRepository",
    "Title",
    "Year",
    "parse_media_id",
]
