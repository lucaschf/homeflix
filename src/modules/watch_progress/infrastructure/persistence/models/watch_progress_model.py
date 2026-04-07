"""WatchProgress ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.config.persistence.base import Base


class WatchProgressModel(Base):
    """SQLAlchemy model for WatchProgress.

    Maps to the 'watch_progresses' table. One row per media item.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
        media_type: Type of media ("movie" or "episode").
        position_seconds: Current playback position.
        duration_seconds: Total duration of the media.
        status: Watch status ("in_progress" or "completed").
        audio_track: Selected audio track index.
        subtitle_track: Selected subtitle track index (-1 = off).
        last_watched_at: Timestamp of last position update.
        completed_at: Timestamp when marked as completed.
    """

    media_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    audio_track: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_track: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_watched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<WatchProgressModel(id={self.id}, media_id={self.media_id!r}, "
            f"status={self.status!r}, position={self.position_seconds})>"
        )


__all__ = ["WatchProgressModel"]
