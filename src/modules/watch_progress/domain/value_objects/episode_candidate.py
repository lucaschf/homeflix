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

from typing import TYPE_CHECKING, ClassVar

from pydantic import ConfigDict

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.modules.watch_progress.domain.value_objects.watchable_media_id import (  # noqa: TCH001 - Pydantic field type, needed at runtime
    WatchableMediaId,
)

if TYPE_CHECKING:
    from src.modules.watch_progress.domain.entities import WatchProgress


class EpisodeCandidate(CompoundValueObject):
    """A single episode weighed by the continue-watching selector.

    Attributes:
        series_id: External series id (``ser_...``).
        media_id: Typed composite episode id keyed by ``WatchProgressRepository``.
        season_number: One-based season number.
        episode_number: One-based episode number within the season.
        episode_title: Display title of the episode (already localized
            upstream, when translations exist).
        duration_seconds: Canonical runtime of the episode, used as a
            fallback when no progress record is present.
        progress: Existing watch-progress record, or ``None`` if the
            episode has never been played.
    """

    # ``progress`` references ``WatchProgress``, which transitively imports
    # this module via ``value_objects/__init__``. Defer build so Pydantic
    # resolves the forward reference once ``entities/__init__`` calls
    # ``EpisodeCandidate.model_rebuild()``.
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        validate_assignment=True,
        extra="forbid",
        defer_build=True,
    )

    series_id: str
    media_id: WatchableMediaId
    season_number: int
    episode_number: int
    episode_title: str
    duration_seconds: int
    progress: WatchProgress | None = None


__all__ = ["EpisodeCandidate"]
