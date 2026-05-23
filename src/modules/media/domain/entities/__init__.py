"""Media domain entities."""

from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    MediaConflict,
    ResolutionAction,
    SuggestedAction,
)
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.entities.season import Season
from src.modules.media.domain.entities.series import Series

# Rebuild models to resolve forward references
Season.model_rebuild()
Series.model_rebuild()

__all__ = [
    "Episode",
    "MatchReason",
    "MediaConflict",
    "Movie",
    "ResolutionAction",
    "ScanRun",
    "ScanRunKind",
    "ScanRunStatus",
    "ScanRunTrigger",
    "Season",
    "Series",
    "SuggestedAction",
]
