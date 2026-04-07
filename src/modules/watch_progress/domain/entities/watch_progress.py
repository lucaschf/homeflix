"""WatchProgress aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.watch_progress.domain.value_objects import ProgressId

_COMPLETION_THRESHOLD = 0.9


class WatchProgress(AggregateRoot[ProgressId]):
    """Tracks playback position for a movie or episode.

    Automatically marks as completed when position reaches 90%
    of the total duration.

    Example:
        >>> progress = WatchProgress.create(
        ...     media_id="mov_abc123def456",
        ...     media_type="movie",
        ...     position_seconds=3600,
        ...     duration_seconds=7200,
        ... )
        >>> progress.percentage
        50.0
    """

    id: ProgressId | None = Field(default=None)

    # What is being watched
    media_id: str
    media_type: str  # "movie" or "episode"

    # Position tracking
    position_seconds: int = Field(ge=0)
    duration_seconds: int = Field(gt=0)
    status: str = Field(default="in_progress")  # "in_progress" or "completed"

    # Track preferences
    audio_track: int | None = None
    subtitle_track: int | None = None

    # Timestamps
    last_watched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def percentage(self) -> float:
        """Calculate watch percentage (0-100)."""
        if self.duration_seconds == 0:
            return 0.0
        return min(100.0, (self.position_seconds / self.duration_seconds) * 100)

    @property
    def is_completed(self) -> bool:
        """Check if the media has been fully watched."""
        return self.status == "completed"

    def update_position(
        self,
        position_seconds: int,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
    ) -> Self:
        """Return a copy with updated position and track preferences.

        Automatically marks as completed if position >= 90% of duration.

        Args:
            position_seconds: Current playback position in seconds.
            audio_track: Selected audio track index.
            subtitle_track: Selected subtitle track index (-1 = off).

        Returns:
            New WatchProgress with updated fields.
        """
        now = datetime.now(UTC)
        ratio = position_seconds / self.duration_seconds if self.duration_seconds else 0
        is_complete = ratio >= _COMPLETION_THRESHOLD

        updates: dict[str, object] = {
            "position_seconds": position_seconds,
            "last_watched_at": now,
        }

        if audio_track is not None:
            updates["audio_track"] = audio_track
        if subtitle_track is not None:
            updates["subtitle_track"] = subtitle_track

        if is_complete and not self.is_completed:
            updates["status"] = "completed"
            updates["completed_at"] = now

        return self.with_updates(**updates)

    @classmethod
    def create(
        cls,
        media_id: str,
        media_type: str,
        position_seconds: int,
        duration_seconds: int,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
    ) -> WatchProgress:
        """Factory method with automatic ID generation.

        Args:
            media_id: External ID of the media (mov_xxx or epi_xxx).
            media_type: Type of media ("movie" or "episode").
            position_seconds: Current playback position in seconds.
            duration_seconds: Total duration of the media in seconds.
            audio_track: Selected audio track index.
            subtitle_track: Selected subtitle track index.

        Returns:
            A new WatchProgress instance.
        """
        now = datetime.now(UTC)
        ratio = position_seconds / duration_seconds if duration_seconds else 0
        is_complete = ratio >= _COMPLETION_THRESHOLD

        return cls(
            id=ProgressId.generate(),
            media_id=media_id,
            media_type=media_type,
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            status="completed" if is_complete else "in_progress",
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            last_watched_at=now,
            completed_at=now if is_complete else None,
        )


__all__ = ["WatchProgress"]
