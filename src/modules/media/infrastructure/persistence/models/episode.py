"""Episode ORM model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base

if TYPE_CHECKING:
    from src.modules.media.infrastructure.persistence.models.media_file import MediaFileModel
    from src.modules.media.infrastructure.persistence.models.season import SeasonModel


class EpisodeModel(Base):
    """SQLAlchemy model for Episode entity.

    Maps to the 'episodes' table. Uses external_id (epi_xxx) for API exposure.
    Belongs to a Season.

    Attributes:
        season_id: Foreign key to parent season (internal ID).
        series_external_id: External ID of parent series (ser_xxx).
        season_number: Season number this episode belongs to.
        episode_number: Episode number within the season.
        title: Episode title.
        synopsis: Episode overview.
        duration: Duration in seconds.
        file_path: Absolute path to video file.
        file_size: File size in bytes.
        resolution: Video resolution (e.g., "1080p").
        thumbnail_path: Path to thumbnail image.
        air_date: Original air date.
        season: Parent season relationship.
    """

    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "episode_number",
            name="uq_episode_season_number",
        ),
        # Non-unique lookup index on the denormalized primary-file path.
        # Uniqueness is intentionally NOT enforced here: ADR-030 lets several
        # episodes share one physical file as disjoint segments, so two live
        # episode rows may legitimately carry the same flat ``file_path``. The
        # authoritative per-``(path, segment)`` guard lives on ``media_files``
        # (``ux_media_file_path_segment``).
        Index(
            "ix_episodes_file_path",
            "file_path",
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    # Relationships
    season_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    series_external_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Episode identification
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Content info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)  # seconds

    # Per-language title/synopsis overrides as a JSON object
    # ({lang: {title, synopsis}}). Null when only English is stored.
    localized: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File info (nullable when no primary file variant exists)
    file_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # bytes
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scrub_preview_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Metadata
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Skip-intro support: flat columns persisting the IntroMarker VO. All
    # fields are NULL when no intro has been set yet (auto job hasn't run
    # AND no manual override). When ``intro_start_seconds`` is non-NULL,
    # the remaining columns must form a valid IntroMarker (enforced by the
    # mapper, not the schema, to keep the migration cheap).
    intro_start_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intro_end_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intro_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    intro_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    intro_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Skip-credits support: flat columns persisting the CreditsMarker VO.
    # Credits run to the end, so only the onset is stored (no end column).
    # All marker fields are NULL until a marker is set; the per-file
    # detection lifecycle is tracked separately by ``credits_detection_state``.
    credits_start_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    credits_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    credits_detected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credits_detection_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_STARTED", server_default="NOT_STARTED"
    )

    # Relationships
    file_variants: Mapped[list["MediaFileModel"]] = relationship(
        "MediaFileModel",
        back_populates="episode",
        cascade="all, delete-orphan",
    )
    season: Mapped["SeasonModel"] = relationship(
        "SeasonModel",
        back_populates="episodes",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<EpisodeModel(id={self.id}, external_id={self.external_id!r}, "
            f"S{self.season_number:02d}E{self.episode_number:02d}, "
            f"title={self.title!r})>"
        )


__all__ = ["EpisodeModel"]
