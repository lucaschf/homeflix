"""Movie ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base

if TYPE_CHECKING:
    from src.modules.media.infrastructure.persistence.models.media_file import MediaFileModel


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

    __table_args__ = (
        # Partial unique index: file_path is unique only among live rows.
        # A soft-deleted movie (e.g. one promoted to a series) keeps its
        # path but must not block a rescan from registering the same file.
        Index(
            "ix_movies_file_path",
            "file_path",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    # Library scoping (lib_xxx prefixed external id; cross-BC string
    # reference, no FK because the catalog and library tables live in
    # different bounded contexts).
    library_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Core info
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)  # seconds
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Images
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scrub_preview_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Categorization (stored as comma-separated for simplicity)
    genres: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # File info (nullable when no primary file variant exists)
    file_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # bytes
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Credits (stored as JSON arrays of names)
    cast: Mapped[str | None] = mapped_column(Text, nullable=True)
    directors: Mapped[str | None] = mapped_column(Text, nullable=True)
    writers: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification (e.g., "PG-13", "R", "14")
    content_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Trailer (YouTube URL)
    trailer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Collection / franchise on TMDB (denormalized as 3 columns since
    # we don't have a Collection aggregate of our own yet)
    collection_tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collection_parts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Localized metadata (JSON: {"pt-BR": {"title": "...", "synopsis": "...", "genres": [...]}})
    localized: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External IDs for metadata enrichment
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Flag set when enrichment couldn't resolve a TMDB match.
    # Indexed so the admin "needs review" listing scans cheaply even
    # as the catalog grows past tens of thousands of rows.
    needs_enrichment_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )

    # Skip-credits support: flat columns persisting the CreditsMarker VO.
    # Credits run to the end, so only the onset is stored (no end column).
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
        back_populates="movie",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<MovieModel(id={self.id}, external_id={self.external_id!r}, "
            f"title={self.title!r}, year={self.year})>"
        )


__all__ = ["MovieModel"]
