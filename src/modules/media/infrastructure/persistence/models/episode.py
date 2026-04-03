"""Episode ORM model."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.persistence.base import Base

if TYPE_CHECKING:
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

    # File info (nullable when no primary file variant exists)
    file_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        unique=True,
        index=True,
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # bytes
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Metadata
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships
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
