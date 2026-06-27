"""Domain events for the Media bounded context."""

from dataclasses import dataclass

from src.building_blocks.domain.events import DomainEvent
from src.shared_kernel.value_objects.media_id import (
    EpisodeId,
    MovieId,
    SeasonId,
    SeriesId,
)
from src.shared_kernel.value_objects.media_type import MediaType


@dataclass(frozen=True, kw_only=True)
class MediaCreatedEvent(DomainEvent):
    """Emitted when a new movie or series is created.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media (:class:`MediaType`).
    """

    media_id: MovieId | SeriesId
    media_type: MediaType


@dataclass(frozen=True, kw_only=True)
class IntroDetectedEvent(DomainEvent):
    """Emitted when the auto-detection job persists an intro marker.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        season_id: External ID of the parent season (ssn_xxx).
        series_id: External ID of the parent series (ser_xxx).
        start_seconds: Start of the detected intro segment.
        end_seconds: End of the detected intro segment.
        confidence: Detection confidence in ``[0.0, 1.0]``.
    """

    episode_id: EpisodeId
    season_id: SeasonId
    series_id: SeriesId
    start_seconds: int = 0
    end_seconds: int = 0
    confidence: float = 0.0


@dataclass(frozen=True, kw_only=True)
class IntroManuallySetEvent(DomainEvent):
    """Emitted when a user sets or edits an intro marker via the API.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        series_id: External ID of the parent series (ser_xxx).
        start_seconds: Start of the manually-set intro segment.
        end_seconds: End of the manually-set intro segment.
    """

    episode_id: EpisodeId
    series_id: SeriesId
    start_seconds: int = 0
    end_seconds: int = 0


@dataclass(frozen=True, kw_only=True)
class IntroClearedEvent(DomainEvent):
    """Emitted when an episode's intro marker is removed.

    Used when an operator clears a marker — typically to let the
    auto-detection job re-process the episode on its next tick.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        series_id: External ID of the parent series (ser_xxx).
    """

    episode_id: EpisodeId
    series_id: SeriesId


@dataclass(frozen=True, kw_only=True)
class MediaConflictDetectedEvent(DomainEvent):
    """Emitted when the dedup detector queues a new conflict.

    Fires after a content-identity match (ADR-015) creates a
    ``MediaConflict`` row in the admin queue. Downstream handlers
    can use it for notifications (e.g. "you have N pending
    conflicts") without polling the table.

    Attributes:
        conflict_id: External id of the queued conflict (``cnf_xxx``).
        candidate_a_id: One side of the matched pair.
        candidate_b_id: The other side.
        match_reason: Which identity rule fired (``tmdb_id`` or
            ``title_year_fallback``).
        suggested_action: Pre-computed hint shown to the admin
            (``likely_same_release`` or ``different_edit_suspected``).
    """

    conflict_id: str = ""
    candidate_a_id: MovieId | SeriesId
    candidate_b_id: MovieId | SeriesId
    match_reason: str = ""
    suggested_action: str = ""


__all__ = [
    "IntroClearedEvent",
    "IntroDetectedEvent",
    "IntroManuallySetEvent",
    "MediaConflictDetectedEvent",
    "MediaCreatedEvent",
]
