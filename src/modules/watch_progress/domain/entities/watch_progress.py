"""WatchProgress aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.watch_progress.domain.value_objects import (
    ProgressId,
    WatchableMediaType,
    WatchStatus,
)
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001

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

    # Owner — every progress row belongs to exactly one profile
    profile_id: ProfileId

    # What is being watched
    media_id: str
    media_type: WatchableMediaType

    # Position tracking
    position_seconds: int = Field(ge=0)
    duration_seconds: int = Field(gt=0)
    status: WatchStatus = Field(default=WatchStatus.IN_PROGRESS)

    # Track preferences
    audio_track: int | None = None
    subtitle_track: int | None = None

    # Timestamps
    last_watched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @staticmethod
    def _watched_ratio(position_seconds: int, duration_seconds: int | None) -> float:
        """Fraction of the media watched (0.0+); 0.0 when duration is unknown.

        Single source of the position/duration formula shared by
        ``percentage`` and the completion check so the two never drift.
        """
        if not duration_seconds:
            return 0.0
        return position_seconds / duration_seconds

    @classmethod
    def _reaches_completion(cls, position_seconds: int, duration_seconds: int | None) -> bool:
        """Whether the watched ratio crosses the completion threshold."""
        return cls._watched_ratio(position_seconds, duration_seconds) >= _COMPLETION_THRESHOLD

    @property
    def percentage(self) -> float:
        """Calculate watch percentage (0-100)."""
        return min(100.0, self._watched_ratio(self.position_seconds, self.duration_seconds) * 100)

    @property
    def is_completed(self) -> bool:
        """Check if the media has been fully watched."""
        return self.status == WatchStatus.COMPLETED

    def update_position(
        self,
        position_seconds: int,
        duration_seconds: int | None = None,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
    ) -> Self:
        """Return a copy with updated position and track preferences.

        Automatically marks as completed if position >= 90% of duration.

        Args:
            position_seconds: Current playback position in seconds.
            duration_seconds: Updated total duration (corrects stale values).
            audio_track: Selected audio track index.
            subtitle_track: Selected subtitle track index (-1 = off).

        Returns:
            New WatchProgress with updated fields.
        """
        now = datetime.now(UTC)
        effective_duration = duration_seconds or self.duration_seconds
        is_complete = self._reaches_completion(position_seconds, effective_duration)

        updates: dict[str, object] = {
            "position_seconds": position_seconds,
            "last_watched_at": now,
        }

        if duration_seconds is not None:
            updates["duration_seconds"] = duration_seconds
        if audio_track is not None:
            updates["audio_track"] = audio_track
        if subtitle_track is not None:
            updates["subtitle_track"] = subtitle_track

        if is_complete and not self.is_completed:
            updates["status"] = WatchStatus.COMPLETED
            updates["completed_at"] = now

        return self.with_updates(**updates)

    @classmethod
    def create(
        cls,
        profile_id: ProfileId,
        media_id: str,
        media_type: WatchableMediaType,
        position_seconds: int,
        duration_seconds: int,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
    ) -> WatchProgress:
        """Factory method with automatic ID generation.

        Args:
            profile_id: Owning profile (``prf_xxx``). Every progress
                row is scoped to a single profile so multi-profile
                households watch independently.
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
        is_complete = cls._reaches_completion(position_seconds, duration_seconds)

        return cls(
            id=ProgressId.generate(),
            profile_id=profile_id,
            media_id=media_id,
            media_type=media_type,
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            status=WatchStatus.COMPLETED if is_complete else WatchStatus.IN_PROGRESS,
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            last_watched_at=now,
            completed_at=now if is_complete else None,
        )


__all__ = ["WatchProgress"]
