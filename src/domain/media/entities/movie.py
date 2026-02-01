"""Movie aggregate root."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from src.domain.media.value_objects import (
    Duration,
    FilePath,
    Genre,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.domain.shared.models import AggregateRoot


class Movie(AggregateRoot):
    """Movie aggregate root.

    Represents a movie with its metadata and file information.
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

    model_config: ClassVar[ConfigDict] = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    # Identity - override base id type
    id: MovieId | None = Field(default=None)

    # Core info
    title: Title
    original_title: Title | None = None
    year: Year
    duration: Duration
    synopsis: str | None = Field(default=None, max_length=10000)

    # Images
    poster_path: FilePath | None = None
    backdrop_path: FilePath | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)

    # File info
    file_path: FilePath
    file_size: int = Field(ge=0)  # bytes
    resolution: Resolution

    # External IDs for metadata enrichment
    tmdb_id: int | None = None
    imdb_id: str | None = Field(default=None, pattern=r"^tt\d{7,}$")

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
    def convert_genres(cls, v: list | None) -> list[Genre]:
        """Convert string list to Genre list."""
        return [] if v is None else [Genre(g) if isinstance(g, str) else g for g in v]

    def add_genre(self, genre: Genre | str) -> None:
        """Add a genre to this movie.

        Args:
            genre: The genre to add (string or Genre object).
        """
        if isinstance(genre, str):
            genre = Genre(genre)
        if genre not in self.genres:
            self.genres.append(genre)
            self.touch()

    @classmethod
    def create(
        cls,
        title: str | Title,
        year: int | Year,
        duration: int | Duration,
        file_path: str | FilePath,
        file_size: int,
        resolution: str | Resolution,
        **kwargs,
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

        return cls(
            id=movie_id,
            title=title,
            year=year,
            duration=duration,
            file_path=file_path,
            file_size=file_size,
            resolution=resolution,
            **kwargs,
        )


__all__ = ["Movie"]
