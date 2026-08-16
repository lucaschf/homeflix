"""WatchProgress aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import Field, model_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.watch_progress.domain.value_objects import (
    PlaybackPosition,
    ProgressId,
    SubtitlePreference,
    WatchableMediaId,
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
    media_id: WatchableMediaId
    media_type: WatchableMediaType

    @model_validator(mode="after")
    def _validate_media_id_matches_type(self) -> Self:
        """Reject a movie id paired with episode type and vice versa."""
        if self.media_id.is_movie != (self.media_type is WatchableMediaType.MOVIE):
            raise ValueError(
                f"media_id '{self.media_id.value}' does not match "
                f"media_type '{self.media_type.value}'",
            )
        return self

    # Position tracking — position + duration bundled so the progress
    # arithmetic (ratio/percentage/completion) lives on the value object.
    position: PlaybackPosition
    status: WatchStatus = Field(default=WatchStatus.IN_PROGRESS)

    # Track preferences
    audio_track: int | None = None
    subtitle_track: SubtitlePreference | None = None

    # Timestamps
    last_watched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def position_seconds(self) -> int:
        """Current playback position in seconds (from the position VO)."""
        return self.position.position_seconds

    @property
    def duration_seconds(self) -> int:
        """Total media duration in seconds (from the position VO)."""
        return self.position.duration_seconds

    @property
    def percentage(self) -> float:
        """Calculate watch percentage (0-100)."""
        return self.position.percentage

    @property
    def is_completed(self) -> bool:
        """Check if the media has been fully watched."""
        return self.status == WatchStatus.COMPLETED

    def update_position(
        self,
        position_seconds: int,
        duration_seconds: int | None = None,
        audio_track: int | None = None,
        subtitle_track: SubtitlePreference | None = None,
    ) -> Self:
        """Return a copy with updated position and track preferences.

        Automatically marks as completed if position >= 90% of duration.

        Args:
            position_seconds: Current playback position in seconds.
            duration_seconds: Updated total duration (corrects stale values).
            audio_track: Selected audio track index, or ``None`` to leave
                the current preference unchanged.
            subtitle_track: New subtitle preference, or ``None`` to leave
                the current preference unchanged.

        Returns:
            New WatchProgress with updated fields.
        """
        now = datetime.now(UTC)
        effective_duration = duration_seconds or self.duration_seconds
        new_position = PlaybackPosition(
            position_seconds=position_seconds,
            duration_seconds=effective_duration,
        )
        is_complete = new_position.reaches_completion(_COMPLETION_THRESHOLD)

        updates: dict[str, object] = {
            "position": new_position,
            "last_watched_at": now,
        }

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
        media_id: WatchableMediaId,
        media_type: WatchableMediaType,
        position_seconds: int,
        duration_seconds: int,
        audio_track: int | None = None,
        subtitle_track: SubtitlePreference | None = None,
    ) -> WatchProgress:
        """Factory method with automatic ID generation.

        Args:
            profile_id: Owning profile (``prf_xxx``). Every progress
                row is scoped to a single profile so multi-profile
                households watch independently.
            media_id: Typed watchable id (``mov_xxx`` or the composite
                ``epi_ser_xxx_S_E``); must match ``media_type``.
            media_type: Type of media ("movie" or "episode").
            position_seconds: Current playback position in seconds.
            duration_seconds: Total duration of the media in seconds.
            audio_track: Selected audio track index.
            subtitle_track: Subtitle preference (off or a track), or
                ``None`` when no preference was recorded.

        Returns:
            A new WatchProgress instance.
        """
        now = datetime.now(UTC)
        position = PlaybackPosition(
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
        )
        is_complete = position.reaches_completion(_COMPLETION_THRESHOLD)

        return cls(
            id=ProgressId.generate(),
            profile_id=profile_id,
            media_id=media_id,
            media_type=media_type,
            position=position,
            status=WatchStatus.COMPLETED if is_complete else WatchStatus.IN_PROGRESS,
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            last_watched_at=now,
            completed_at=now if is_complete else None,
        )


__all__ = ["WatchProgress"]
