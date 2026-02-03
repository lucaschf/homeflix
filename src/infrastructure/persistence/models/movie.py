"""Movie ORM model."""

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class MovieModel(Base):
    """SQLAlchemy model for Movie aggregate.

    Maps to the 'movies' table. Use external_id (mov_xxx) for API exposure.

    Attributes:
        title: Display title of the movie.
        original_title: Original language title, if different.
        year: Release year.
        duration: Duration in seconds.
        synopsis: Plot summary.
        poster_path: Path to poster image.
        backdrop_path: Path to backdrop image.
        genres: Comma-separated list of genres.
        file_path: Absolute path to video file.
        file_size: File size in bytes.
        resolution: Video resolution (e.g., "1080p", "4K").
        tmdb_id: The Movie Database ID.
        imdb_id: IMDb ID (e.g., "tt1234567").
    """

    # Core info
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)  # seconds
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Images
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Categorization (stored as comma-separated for simplicity)
    genres: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # File info
    file_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        unique=True,
        index=True,
    )
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # bytes
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)

    # External IDs for metadata enrichment
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<MovieModel(id={self.id}, external_id={self.external_id!r}, "
            f"title={self.title!r}, year={self.year})>"
        )


__all__ = ["MovieModel"]
