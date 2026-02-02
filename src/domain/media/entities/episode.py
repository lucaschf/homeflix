"""Episode entity for TV series."""

from datetime import date
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from src.domain.media.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Resolution,
    SeriesId,
    Title,
)
from src.domain.shared.models import DomainEntity


class Episode(DomainEntity):
    """Episode entity belonging to a Season of a Series.

    Represents a single episode of a TV series with its metadata
    and file information.

    Example:
        >>> episode = Episode(
        ...     series_id=SeriesId.generate(),
        ...     season_number=1,
        ...     episode_number=1,
        ...     title=Title("Pilot"),
        ...     duration=Duration(2700),
        ...     file_path=FilePath("/series/show/s01e01.mkv"),
        ...     file_size=1_000_000_000,
        ...     resolution=Resolution("1080p"),
        ... )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    # Identity - override base id type
    id: EpisodeId | None = Field(default=None)

    # Relationship
    series_id: SeriesId
    season_number: int = Field(ge=0)  # 0 for specials
    episode_number: int = Field(ge=1)

    # Content info
    title: Title
    synopsis: str | None = Field(default=None, max_length=10000)
    duration: Duration

    # File info
    file_path: FilePath
    file_size: int = Field(ge=0)  # bytes
    resolution: Resolution
    thumbnail_path: FilePath | None = None

    # Metadata
    air_date: date | None = None

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | EpisodeId | None) -> EpisodeId | None:
        """Convert string to EpisodeId if needed."""
        if v is None:
            return None
        return EpisodeId(v) if isinstance(v, str) else v


__all__ = ["Episode"]
