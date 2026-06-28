"""WatchProgress ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class WatchProgressModel(Base):
    """SQLAlchemy model for WatchProgress.

    Maps to the 'watch_progresses' table. One row per (profile, media)
    pair — different profiles in the same household watch the same
    title independently.

    ``profile_id`` is stored as the prefixed external ID (``prf_xxx``)
    rather than the database UUID — cross-BC references never traverse
    UUIDs (per ADR-008), and watch_progress only needs the string
    identity for scoping queries (no JOIN to ``profiles`` is required).

    Attributes:
        profile_id: Owning profile's prefixed external ID.
        media_id: External ID of the media (mov_xxx or epi_xxx).
        media_type: Type of media ("movie" or "episode").
        position_seconds: Current playback position.
        duration_seconds: Total duration of the media.
        status: Watch status ("in_progress" or "completed").
        audio_track: Selected audio track index.
        subtitle_track: Subtitle preference encoded as an int — see
            ``SubtitlePreference.to_wire`` (``-1`` = off, ``>= 0`` = track).
        last_watched_at: Timestamp of last position update.
        completed_at: Timestamp when marked as completed.
    """

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "media_id",
            name="uq_watch_progresses_profile_media",
        ),
    )

    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
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
            f"<WatchProgressModel(id={self.id}, profile_id={self.profile_id!r}, "
            f"media_id={self.media_id!r}, status={self.status!r}, "
            f"position={self.position_seconds})>"
        )


__all__ = ["WatchProgressModel"]
