"""Domain events for the Media bounded context."""

from dataclasses import dataclass

from src.building_blocks.domain.events import DomainEvent


@dataclass(frozen=True)
class MediaCreatedEvent(DomainEvent):
    """Emitted when a new movie or series is created.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
    """

    media_id: str = ""
    media_type: str = ""


@dataclass(frozen=True)
class IntroDetectedEvent(DomainEvent):
    """Emitted when the auto-detection job persists an intro marker.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        season_id: External ID of the parent season (sea_xxx).
        series_id: External ID of the parent series (ser_xxx).
        start_seconds: Start of the detected intro segment.
        end_seconds: End of the detected intro segment.
        confidence: Detection confidence in ``[0.0, 1.0]``.
    """

    episode_id: str = ""
    season_id: str = ""
    series_id: str = ""
    start_seconds: int = 0
    end_seconds: int = 0
    confidence: float = 0.0


@dataclass(frozen=True)
class IntroManuallySetEvent(DomainEvent):
    """Emitted when a user sets or edits an intro marker via the API.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        series_id: External ID of the parent series (ser_xxx).
        start_seconds: Start of the manually-set intro segment.
        end_seconds: End of the manually-set intro segment.
    """

    episode_id: str = ""
    series_id: str = ""
    start_seconds: int = 0
    end_seconds: int = 0


@dataclass(frozen=True)
class IntroClearedEvent(DomainEvent):
    """Emitted when an episode's intro marker is removed.

    Used when an operator clears a marker — typically to let the
    auto-detection job re-process the episode on its next tick.

    Attributes:
        episode_id: External ID of the episode (epi_xxx).
        series_id: External ID of the parent series (ser_xxx).
    """

    episode_id: str = ""
    series_id: str = ""


@dataclass(frozen=True)
class MoviePromotedToSeriesEvent(DomainEvent):
    """Emitted when an admin promotes a movie into a series.

    Driven by the cross-type relink flow (e.g. ``Salem's Lot (1979)``,
    which TMDB catalogs as a TV miniseries rather than a film).

    The original movie row is soft-deleted; a new series + season
    + episodes structure takes its place. All file variants of the
    movie are reattached to the first episode (``first_episode_id``)
    so external bounded contexts know where playback state should
    migrate (or — per the agreed design — where to delete it).

    Cross-BC handlers:
        - ``watch_progress`` deletes WatchProgress rows for the old
          movie id (safer than mapping a position across a possibly
          re-cut episode boundary).
        - ``collections`` rewrites watchlist + custom-list entries
          to point at the new series id.

    Attributes:
        movie_id: External ID of the source movie (mov_xxx).
        series_id: External ID of the new series (ser_xxx).
        first_episode_id: External ID of the first episode (epi_xxx)
            that now owns the movie's file variants.
    """

    movie_id: str = ""
    series_id: str = ""
    first_episode_id: str = ""


__all__ = [
    "IntroClearedEvent",
    "IntroDetectedEvent",
    "IntroManuallySetEvent",
    "MediaCreatedEvent",
    "MoviePromotedToSeriesEvent",
]
