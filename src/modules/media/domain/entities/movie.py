"""Movie aggregate root."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    TmdbId,
    Year,
)


class Movie(FileVariantMixin, AggregateRoot[MovieId]):
    """Movie aggregate root.

    Represents a movie with its metadata and file variants.
    This is the main entry point for movie-related operations.

    Example:
        >>> movie = Movie.create(
        ...     title="Inception",
        ...     year=2010,
        ...     duration=8880,
        ...     file_path="/movies/inception.mkv",
        ...     file_size=4_000_000_000,
        ...     resolution="1080p",
        ... )
    """

    # Identity
    id: MovieId | None = Field(default=None)

    # Core info
    title: Title
    original_title: Title | None = None
    year: Year
    duration: Duration
    synopsis: str | None = Field(default=None, max_length=10000)

    # Images
    poster_path: ImageUrl | None = None
    backdrop_path: ImageUrl | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)

    # File variants
    files: list[MediaFile] = Field(default_factory=list)

    # Credits
    cast: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    writers: list[str] = Field(default_factory=list)

    # Classification
    content_rating: str | None = None

    # External IDs for metadata enrichment
    tmdb_id: TmdbId | None = None
    imdb_id: ImdbId | None = None

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | MovieId | None) -> MovieId | None:
        """Convert string to MovieId if needed."""
        if v is None:
            return None
        return MovieId(v) if isinstance(v, str) else v

    # noinspection PyNestedDecorators
    @field_validator("genres", mode="before")
    @classmethod
    def convert_genres(cls, v: list[Any] | None) -> list[Genre]:
        """Convert string list to Genre list."""
        return [] if v is None else [Genre(g) if isinstance(g, str) else g for g in v]

    # ── genre helpers ─────────────────────────────────────────────────

    def with_genre(self, genre: Genre | str) -> Self:
        """Return a copy with the genre added.

        Args:
            genre: The genre to add (string or Genre object).

        Returns:
            A new Movie with the genre added, or self if duplicate.
        """
        if isinstance(genre, str):
            genre = Genre(genre)
        if genre in self.genres:
            return self
        return self.with_updates(genres=[*self.genres, genre])

    # ── factory ───────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        title: str | Title,
        year: int | Year,
        duration: int | Duration,
        file_path: str | FilePath,
        file_size: int,
        resolution: str | Resolution,
        **kwargs: Any,
    ) -> Movie:
        """Factory method with automatic ID generation.

        Args:
            title: Movie title.
            year: Release year.
            duration: Duration in seconds.
            file_path: Path to the video file.
            file_size: File size in bytes.
            resolution: Video resolution.
            **kwargs: Additional optional fields.

        Returns:
            A new Movie instance with generated ID.
        """
        movie_id = MovieId.generate()

        if isinstance(title, str):
            title = Title(title)
        if isinstance(year, int):
            year = Year(year)
        if isinstance(duration, int):
            duration = Duration(duration)
        if isinstance(file_path, str):
            file_path = FilePath(file_path)
        if isinstance(resolution, str):
            resolution = Resolution(resolution)

        file = MediaFile(
            file_path=file_path,
            file_size=file_size,
            resolution=resolution,
            is_primary=True,
        )

        return cls(
            id=movie_id,
            title=title,
            year=year,
            duration=duration,
            files=[file],
            **kwargs,
        )


__all__ = ["Movie"]
