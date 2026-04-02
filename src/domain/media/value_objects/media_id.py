"""Media domain external IDs (re-export for backwards compatibility)."""

from src.modules.media.domain.value_objects.media_id import (
    EpisodeId,
    MediaId,
    MovieId,
    SeasonId,
    SeriesId,
    parse_media_id,
)

__all__ = [
    "EpisodeId",
    "MediaId",
    "MovieId",
    "SeasonId",
    "SeriesId",
    "parse_media_id",
]
