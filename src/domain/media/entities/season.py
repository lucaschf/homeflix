"""Season entity for TV series."""

from __future__ import annotations

from datetime import date  # noqa: TCH003
from typing import TYPE_CHECKING, ClassVar

from pydantic import ConfigDict, Field, field_validator

from src.domain.media.value_objects import FilePath, SeasonId, SeriesId, Title
from src.domain.shared.exceptions.domain import BusinessRuleViolationException
from src.domain.shared.models import DomainEntity

if TYPE_CHECKING:
    from src.domain.media import Episode


class Season(DomainEntity):
    """Season entity belonging to a Series, containing Episodes.

    Represents a season of a TV series with its metadata
    and episode collection.

    Example:
        >>> season = Season(
        ...     series_id=SeriesId.generate(),
        ...     season_number=1,
        ...     title=Title("Season One"),
        ... )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    # Identity - override base id type
    id: SeasonId | None = Field(default=None)

    # Relationship
    series_id: SeriesId
    season_number: int = Field(ge=0)  # 0 for specials

    # Content info
    title: Title | None = None
    synopsis: str | None = Field(default=None, max_length=10000)
    poster_path: FilePath | None = None

    # Metadata
    air_date: date | None = None

    # Composition
    episodes: list[Episode] = Field(default_factory=list)

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | SeasonId | None) -> SeasonId | None:
        """Convert string to SeasonId if needed."""
        if v is None:
            return None
        return SeasonId(v) if isinstance(v, str) else v

    @property
    def episode_count(self) -> int:
        """Return the number of episodes in this season.

        Returns:
            The count of episodes.
        """
        return len(self.episodes)

    def add_episode(self, episode: Episode) -> None:
        """Add an episode to this season.

        Args:
            episode: The episode to add.

        Raises:
            BusinessRuleViolationException: If episode series_id or season_number doesn't match.
        """
        if episode.series_id != self.series_id:
            raise BusinessRuleViolationException(
                message="Episode series_id must match Season series_id",
                rule_code="EPISODE_SERIES_MISMATCH",
            )
        if episode.season_number != self.season_number:
            raise BusinessRuleViolationException(
                message="Episode season_number must match Season",
                rule_code="EPISODE_SEASON_MISMATCH",
            )
        self.episodes.append(episode)
        self.touch()

    def get_episode(self, episode_number: int) -> Episode | None:
        """Find an episode by its number.

        Args:
            episode_number: The episode number to find.

        Returns:
            The Episode if found, None otherwise.
        """
        return next(
            (ep for ep in self.episodes if ep.episode_number == episode_number),
            None,
        )


__all__ = ["Season"]
