"""Watch Progress DTOs for application layer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SaveProgressInput:
    """Input for SaveProgressUseCase.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
        media_type: Type of media ("movie" or "episode").
        position_seconds: Current playback position in seconds.
        duration_seconds: Total duration of the media in seconds.
        audio_track: Selected audio track index.
        subtitle_track: Selected subtitle track index (-1 = off).
    """

    media_id: str
    media_type: str
    position_seconds: int
    duration_seconds: int
    audio_track: int | None = None
    subtitle_track: int | None = None


@dataclass(frozen=True)
class GetProgressInput:
    """Input for GetProgressUseCase.

    Attributes:
        media_id: External ID of the media.
    """

    media_id: str


@dataclass(frozen=True)
class ProgressOutput:
    """Output representing watch progress for a media item.

    Attributes:
        media_id: External ID of the media.
        media_type: Type of media.
        position_seconds: Current playback position.
        duration_seconds: Total duration.
        percentage: Watch percentage (0-100).
        status: Watch status ("in_progress" or "completed").
        audio_track: Selected audio track index.
        subtitle_track: Selected subtitle track index.
        last_watched_at: ISO timestamp of last update.
    """

    media_id: str
    media_type: str
    position_seconds: int
    duration_seconds: int
    percentage: float
    status: str
    audio_track: int | None
    subtitle_track: int | None
    last_watched_at: str


@dataclass(frozen=True)
class GetContinueWatchingInput:
    """Input for GetContinueWatchingUseCase.

    Attributes:
        limit: Maximum number of items to return.
        lang: Language code for localized metadata.
    """

    limit: int = 20
    lang: str = "en"


@dataclass(frozen=True)
class ContinueWatchingItem:
    """A single item in the continue watching list.

    Attributes:
        media_id: External ID of the media.
        media_type: Type of media.
        title: Display title (localized).
        poster_path: URL to poster image.
        position_seconds: Current playback position.
        duration_seconds: Total duration.
        percentage: Watch percentage.
        last_watched_at: ISO timestamp of last update.
    """

    media_id: str
    media_type: str
    title: str
    poster_path: str | None
    position_seconds: int
    duration_seconds: int
    percentage: float
    last_watched_at: str


@dataclass(frozen=True)
class ContinueWatchingOutput:
    """Output for GetContinueWatchingUseCase.

    Attributes:
        items: List of continue watching items.
    """

    items: list[ContinueWatchingItem]
