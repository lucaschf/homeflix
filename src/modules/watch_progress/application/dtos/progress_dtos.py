"""Watch Progress DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.watch_progress.domain.entities import WatchProgress


@dataclass(frozen=True)
class SaveProgressInput:
    """Input for SaveProgressUseCase.

    Attributes:
        profile_id: Owning profile (``prf_xxx``) — every row is scoped
            to a single profile so multi-profile households watch
            independently.
        media_id: External ID of the media (mov_xxx or epi_xxx).
        media_type: Type of media ("movie" or "episode").
        position_seconds: Current playback position in seconds.
        duration_seconds: Total duration of the media in seconds.
        audio_track: Selected audio track index.
        subtitle_track: Selected subtitle track index (-1 = off).
    """

    profile_id: str
    media_id: str
    media_type: str
    position_seconds: int
    duration_seconds: int
    audio_track: int | None = None
    subtitle_track: int | None = None


@dataclass(frozen=True)
class GetProgressInput:
    """Input for GetProgressUseCase."""

    profile_id: str
    media_id: str


@dataclass(frozen=True)
class ProgressOutput:
    """Output representing watch progress for a media item."""

    media_id: str
    media_type: str
    position_seconds: int
    duration_seconds: int
    percentage: float
    status: str
    audio_track: int | None
    subtitle_track: int | None
    last_watched_at: str

    @classmethod
    def from_entity(cls, progress: WatchProgress) -> ProgressOutput:
        """Create output DTO from a WatchProgress entity."""
        return cls(
            media_id=progress.media_id.value,
            media_type=progress.media_type,
            position_seconds=progress.position_seconds,
            duration_seconds=progress.duration_seconds,
            percentage=progress.percentage,
            status=progress.status,
            audio_track=progress.audio_track,
            subtitle_track=progress.subtitle_track,
            last_watched_at=progress.last_watched_at.isoformat(),
        )


@dataclass(frozen=True)
class GetContinueWatchingInput:
    """Input for GetContinueWatchingUseCase."""

    profile_id: str
    limit: int = 20
    lang: str = "en"


@dataclass(frozen=True)
class ContinueWatchingItem:
    """A single item in the continue watching list."""

    media_id: str
    media_type: str
    title: str
    poster_path: str | None
    backdrop_path: str | None
    position_seconds: int
    duration_seconds: int
    percentage: float
    last_watched_at: str
    series_id: str | None = None
    series_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None


@dataclass(frozen=True)
class ContinueWatchingOutput:
    """Output for GetContinueWatchingUseCase."""

    items: list[ContinueWatchingItem]
