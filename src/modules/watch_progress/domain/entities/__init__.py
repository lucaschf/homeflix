"""Watch Progress entities."""

from src.modules.watch_progress.domain.entities.watch_progress import WatchProgress
from src.modules.watch_progress.domain.value_objects.episode_candidate import (
    EpisodeCandidate,
)

# ``EpisodeCandidate`` declares ``progress: WatchProgress | None`` as a forward
# reference (the value_objects package is imported by WatchProgress, so the VO
# cannot eager-import the entity). Resolve it here, after both are loaded.
EpisodeCandidate.model_rebuild()

__all__ = ["WatchProgress"]
