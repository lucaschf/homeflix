"""MediaFile ORM model for file variants."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base

if TYPE_CHECKING:
    from src.modules.media.infrastructure.persistence.models.episode import EpisodeModel
    from src.modules.media.infrastructure.persistence.models.movie import MovieModel


class MediaFileModel(Base):
    """SQLAlchemy model for media file variants.

    Maps to the 'media_files' table. Each record represents a single
    file variant (resolution/codec combination) belonging to either
    a Movie or an Episode.

    Attributes:
        movie_id: FK to parent movie (NULL if belongs to episode).
        episode_id: FK to parent episode (NULL if belongs to movie).
        file_path: Absolute path to the video file.
        file_size: File size in bytes.
        resolution_width: Video width in pixels.
        resolution_height: Video height in pixels.
        resolution_name: Human-readable resolution (e.g., "1080p").
        video_codec: Video codec (h264, h265, etc.).
        video_bitrate: Video bitrate in kbps.
        hdr_format: HDR format if applicable.
        is_primary: Whether this is the primary file variant.
        added_at: When this file variant was registered.
        start_offset_seconds: Start of the title's window within a shared
            physical file (ADR-030), or NULL when this variant is the whole
            file.
        end_offset_seconds: Exclusive end of the title's window within a
            shared physical file, or NULL when this variant is the whole file.
        audio_tracks_json: JSON-serialized audio track metadata.
        subtitle_tracks_json: JSON-serialized subtitle track metadata.
    """

    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL AND episode_id IS NULL) OR "
            "(movie_id IS NULL AND episode_id IS NOT NULL)",
            name="ck_media_file_single_owner",
        ),
        # A physical file may be shared by several titles as disjoint time
        # windows (ADR-030), so uniqueness is per ``(path, segment)`` rather
        # than per path. COALESCE gives whole-file rows (NULL offsets) a
        # concrete key so duplicate whole-file registrations are still
        # rejected (SQL treats NULL != NULL, which would otherwise slip
        # duplicates past the index).
        Index(
            "ux_media_file_path_segment",
            "file_path",
            func.coalesce(text("start_offset_seconds"), text("-1")),
            func.coalesce(text("end_offset_seconds"), text("-1")),
            unique=True,
        ),
    )

    # Owner FK (exactly one must be set)
    movie_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    episode_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("episodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # File metadata. ``file_path`` is intentionally NOT globally unique:
    # ADR-030 lets several episodes share one physical file as disjoint
    # segments. Uniqueness is enforced per ``(path, segment)`` by
    # ``ux_media_file_path_segment`` above.
    file_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        index=True,
    )
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Resolution
    resolution_width: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_height: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_name: Mapped[str] = mapped_column(String(20), nullable=False)

    # Video technical info
    video_codec: Mapped[str | None] = mapped_column(String(20), nullable=True)
    video_bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hdr_format: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Time window within a shared physical file (ADR-030). Both NULL when
    # this variant is the whole file (the default, backward-compatible case).
    start_offset_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Flags
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Track metadata (JSON-serialized)
    audio_tracks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_tracks_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    movie: Mapped["MovieModel | None"] = relationship(
        "MovieModel",
        back_populates="file_variants",
    )
    episode: Mapped["EpisodeModel | None"] = relationship(
        "EpisodeModel",
        back_populates="file_variants",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        owner = f"movie_id={self.movie_id}" if self.movie_id else f"episode_id={self.episode_id}"
        return (
            f"<MediaFileModel(id={self.id}, {owner}, "
            f"resolution={self.resolution_name!r}, primary={self.is_primary})>"
        )


__all__ = ["MediaFileModel"]
