"""Series aggregate root."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import Field, field_validator, model_validator

from src.building_blocks.domain import AggregateRoot
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.building_blocks.domain.events import MediaCreatedEvent
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    Genre,
    ImageUrl,
    ImdbId,
    SeriesId,
    Title,
    TmdbId,
    Year,
)

if TYPE_CHECKING:
    from src.modules.media.domain.entities.season import Season


class Series(AggregateRoot[SeriesId]):
    """Series aggregate root containing Seasons and Episodes.

    Represents a TV series with its metadata and season/episode structure.
    This is the main entry point for series-related operations.

    Example:
        >>> series = Series.create(
        ...     title="Breaking Bad",
        ...     start_year=2008,
        ... )
    """

    # Identity
    id: SeriesId | None = Field(default=None)

    # Core info
    title: Title
    original_title: Title | None = None
    start_year: Year
    end_year: Year | None = None  # None means still ongoing
    synopsis: str | None = Field(default=None, max_length=10000)

    # Images
    poster_path: ImageUrl | None = None
    backdrop_path: ImageUrl | None = None

    # Categorization
    genres: list[Genre] = Field(default_factory=list)
    content_rating: str | None = None
    trailer_url: str | None = None

    # Localized metadata
    localized: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # External IDs
    tmdb_id: TmdbId | None = None
    imdb_id: ImdbId | None = None

    # Composition
    seasons: list[Season] = Field(default_factory=list)

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | SeriesId | None) -> SeriesId | None:
        """Convert string to SeriesId if needed."""
        if v is None:
            return None

        return SeriesId(v) if isinstance(v, str) else v

    # -- Localized accessors ---------------------------------------------------

    def get_title(self, lang: str = "en") -> str:
        """Get title in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        return str(loc.get("title") or self.title.value)

    def get_synopsis(self, lang: str = "en") -> str | None:
        """Get synopsis in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        return str(loc["synopsis"]) if loc.get("synopsis") else self.synopsis

    def get_genres(self, lang: str = "en") -> list[str]:
        """Get genres in the requested language, falling back to default."""
        loc = self.localized.get(lang, {})
        loc_genres = loc.get("genres")
        if loc_genres and isinstance(loc_genres, list):
            return [str(g) for g in loc_genres]
        return [g.value for g in self.genres]

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
        """Check if the series is still ongoing.

        Returns:
            True if series has no end_year.
        """
        return self.end_year is None

    def with_season(self, season: Season) -> Self:
        """Return a copy with the season added.

        Args:
            season: The season to add.

        Returns:
            A new Series with the season added, or self if already present.

        Raises:
            BusinessRuleViolationException: If season series_id doesn't match.
        """
        if season.series_id != self.id:
            raise BusinessRuleViolationException(
                message="Season series_id must match Series id",
                rule_code=MediaRuleCodes.SEASON_SERIES_MISMATCH,
            )
        if season in self.seasons:
            return self
        return self.with_updates(seasons=[*self.seasons, season])

    def get_season(self, season_number: int) -> Season | None:
        """Find a season by its number.

        Args:
            season_number: The season number to find.

        Returns:
            The Season if found, None otherwise.
        """
        return next(
            (season for season in self.seasons if season.season_number == season_number),
            None,
        )

    @classmethod
    def create(
        cls,
        title: str | Title,
        start_year: int | Year,
        **kwargs: Any,
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

        series = cls(
            id=series_id,
            title=title,
            start_year=start_year,
            **kwargs,
        )
        series.add_event(MediaCreatedEvent(media_id=str(series_id), media_type="series"))
        return series


__all__ = ["Series"]
