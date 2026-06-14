"""Series ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base

if TYPE_CHECKING:
    from src.modules.media.infrastructure.persistence.models.season import SeasonModel


class SeriesModel(Base):
    """SQLAlchemy model for Series aggregate.

    Maps to the 'series' table. Use external_id (ser_xxx) for API exposure.
    Contains seasons via cascade relationship.

    Attributes:
        title: Display title of the series.
        original_title: Original language title, if different.
        start_year: Year the series started.
        end_year: Year the series ended (None if ongoing).
        synopsis: Plot summary.
        poster_path: Path to poster image.
        backdrop_path: Path to backdrop image.
        genres: Comma-separated list of genres.
        tmdb_id: The Movie Database ID.
        imdb_id: IMDb ID.
        seasons: Related season records.
    """

    # Library scoping (lib_xxx prefixed external id; cross-BC string
    # reference, no FK because the catalog and library tables live in
    # different bounded contexts).
    library_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Core info
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Images
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Categorization
    genres: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trailer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Credits — same JSON-array-of-cast-dicts shape MovieModel uses.
    cast: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Localized metadata (JSON)
    localized: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External IDs
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Flag set when enrichment couldn't resolve a TMDB match or an
    # operator marked the result as wrong. Indexed so the admin "needs
    # review" listing scans cheaply as the catalog grows.
    needs_enrichment_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )

    # Relationships
    seasons: Mapped[list["SeasonModel"]] = relationship(
        "SeasonModel",
        back_populates="series",
        cascade="all, delete-orphan",
        order_by="SeasonModel.season_number",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<SeriesModel(id={self.id}, external_id={self.external_id!r}, "
            f"title={self.title!r}, start_year={self.start_year})>"
        )


__all__ = ["SeriesModel"]
