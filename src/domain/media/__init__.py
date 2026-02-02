"""Media Catalog bounded context.

This module contains the domain model for media content (movies, series).
"""

from src.domain.media.entities import Episode, Movie, Season, Series
from src.domain.media.repositories import MovieRepository, SeriesRepository
from src.domain.media.value_objects import (
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
