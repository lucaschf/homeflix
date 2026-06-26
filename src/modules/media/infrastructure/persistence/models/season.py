"""Season ORM model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base

if TYPE_CHECKING:
    from src.modules.media.infrastructure.persistence.models.episode import EpisodeModel
    from src.modules.media.infrastructure.persistence.models.series import SeriesModel


class SeasonModel(Base):
    """SQLAlchemy model for Season entity.

    Maps to the 'seasons' table. Use external_id (ssn_xxx) for API exposure.
    Belongs to a Series and contains Episodes.

    Attributes:
        series_id: Foreign key to parent series (internal ID).
        series_external_id: External ID of parent series (ser_xxx).
        season_number: Season number (0 for specials).
        title: Optional season title.
        synopsis: Season overview.
        poster_path: Path to season poster.
        air_date: First air date of the season.
        series: Parent series relationship.
        episodes: Child episode relationships.
    """

    __table_args__ = (
        UniqueConstraint("series_id", "season_number", name="uq_season_series_number"),
    )

    # Relationships
    series_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("series.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    series_external_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Season info
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Per-language title/synopsis overrides as a JSON object
    # ({lang: {title, synopsis}}). Null when only English is stored.
    localized: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Intro detection job state (per-Season; manual markers on individual
    # episodes are independent of this column). Default NOT_STARTED so
    # backfilled rows enter the detection queue automatically.
    intro_detection_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="NOT_STARTED",
        server_default="NOT_STARTED",
    )
    intro_detection_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Episode count (non-deleted) at the last attempt. An
    # INSUFFICIENT_EPISODES season is only re-attempted once its current
    # count grows past this, so a permanently-small season stops being
    # retried every tick. NULL means "never stamped" (re-eligible once).
    intro_detection_attempted_episode_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    intro_detection_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    series: Mapped["SeriesModel"] = relationship(
        "SeriesModel",
        back_populates="seasons",
    )
    episodes: Mapped[list["EpisodeModel"]] = relationship(
        "EpisodeModel",
        back_populates="season",
        cascade="all, delete-orphan",
        order_by="EpisodeModel.episode_number",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<SeasonModel(id={self.id}, external_id={self.external_id!r}, "
            f"series_id={self.series_id}, season_number={self.season_number})>"
        )


__all__ = ["SeasonModel"]
