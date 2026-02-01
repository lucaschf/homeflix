"""Series aggregate root."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from src.domain.media.value_objects import FilePath, Genre, SeriesId, Title, Year
from src.domain.shared.models import AggregateRoot


class Series(AggregateRoot):
    """Series aggregate root containing Seasons and Episodes.

    Represents a TV series with its metadata and season/episode structure.
    This is the main entry point for series-related operations.

    Example:
        >>> series = Series.create(
        ...     title="Breaking Bad",
        ...     start_year=2008,
        ... )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    # Identity - override base id type
    id: SeriesId | None = Field(default=None)

    # Core info
    title: Title
    original_title: Title | None = None
    start_year: Year
    end_year: Year | None = None  # None means still ongoing
    synopsis: str | None = Field(default=None, max_length=10000)

    # Images
    poster_path: FilePath | None = None
    backdrop_path: FilePath | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)

    # External IDs
    tmdb_id: int | None = None
    imdb_id: str | None = Field(default=None, pattern=r"^tt\d{7,}$")

    # Composition - using string annotation to avoid circular import
    seasons: list[Season] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | SeriesId | None) -> SeriesId | None:
        """Convert string to SeriesId if needed."""
        if v is None:
            return None
        if isinstance(v, str):
            return SeriesId(v)
        return v

    @model_validator(mode="after")
    def validate_year_range(self) -> Series:
        """Ensure end_year >= start_year if end_year is set."""
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year cannot be before start_year")
        return self

    @property
    def season_count(self) -> int:
        """Return the number of seasons.

        Returns:
            The count of seasons.
        """
        return len(self.seasons)

    @property
    def total_episodes(self) -> int:
        """Return total episode count across all seasons.

        Returns:
            The total number of episodes in all seasons.
        """
        return sum(s.episode_count for s in self.seasons)

    @property
    def is_ongoing(self) -> bool:
        """Check if series is still ongoing.

        Returns:
            True if series has no end_year.
        """
        return self.end_year is None

    def add_season(self, season: Season) -> None:
        """Add a season to this series.

        Args:
            season: The season to add.

        Raises:
            ValueError: If season series_id doesn't match.
        """
        if season.series_id != self.id:
            raise ValueError("Season series_id must match Series id")
        self.seasons.append(season)
        self.touch()

    def get_season(self, season_number: int) -> Season | None:
        """Find a season by its number.

        Args:
            season_number: The season number to find.

        Returns:
            The Season if found, None otherwise.
        """
        for season in self.seasons:
            if season.season_number == season_number:
                return season
        return None

    @classmethod
    def create(
        cls,
        title: str | Title,
        start_year: int | Year,
        **kwargs,
    ) -> Series:
        """Factory method with automatic ID generation.

        Args:
            title: Series title.
            start_year: First season year.
            **kwargs: Additional optional fields.

        Returns:
            A new Series instance with generated ID.
        """
        series_id = SeriesId.generate()

        if isinstance(title, str):
            title = Title(title)
        if isinstance(start_year, int):
            start_year = Year(start_year)

        return cls(
            id=series_id,
            title=title,
            start_year=start_year,
            **kwargs,
        )


from src.domain.media.entities.season import Season  # noqa: E402, TCH001

__all__ = ["Series"]
