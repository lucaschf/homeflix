"""Media domain external IDs.

``MediaId`` and its concrete types moved to the shared_kernel
(ADR-018) because they are consumed by ``watch_progress``,
``collections`` and ``catalog_requests`` in addition to this module.
This re-export keeps the historical import path working while callers
migrate incrementally.
"""

from src.shared_kernel.value_objects.media_id import (
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
