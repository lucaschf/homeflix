"""EpisodeCandidate value object — input shape for ``ContinueWatchingSelector``.

Carries the minimum an episode needs to participate in the
"which episode should the user resume?" decision:

* its series/episode coordinates,
* the composite media id keyed by the watch progress repo,
* the optional ``WatchProgress`` for that id.

Lives in the domain so the selector can operate on pure domain
types with no awareness of the application ports that happened to
produce them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.watch_progress.domain.entities import WatchProgress


@dataclass(frozen=True)
class EpisodeCandidate:
    """A single episode weighed by the continue-watching selector.

    Attributes:
        series_id: External series id (``ser_...``).
        media_id: Composite episode id keyed by ``WatchProgressRepository``.
        season_number: One-based season number.
        episode_number: One-based episode number within the season.
        episode_title: Display title of the episode (already localized
            upstream, when translations exist).
        duration_seconds: Canonical runtime of the episode, used as a
            fallback when no progress record is present.
        progress: Existing watch-progress record, or ``None`` if the
            episode has never been played.
    """

    series_id: str
    media_id: str
    season_number: int
    episode_number: int
    episode_title: str
    duration_seconds: int
    progress: WatchProgress | None


__all__ = ["EpisodeCandidate"]
