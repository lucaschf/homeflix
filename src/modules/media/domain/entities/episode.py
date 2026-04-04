"""Episode entity for TV series."""

from __future__ import annotations

from pydantic import Field, field_validator

from src.building_blocks.domain import DomainEntity
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.value_objects import (
    AirDate,
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    SeriesId,
    Title,
)


class Episode(FileVariantMixin, DomainEntity[EpisodeId]):
    """Episode entity belonging to a Season of a Series.

    Represents a single episode of a TV series with its metadata
    and file variants.

    Example:
        >>> episode = Episode(
        ...     series_id=SeriesId.generate(),
        ...     season_number=1,
        ...     episode_number=1,
        ...     title=Title("Pilot"),
        ...     duration=Duration(2700),
        ...     files=[MediaFile(
        ...         file_path=FilePath("/series/show/s01e01.mkv"),
        ...         file_size=1_000_000_000,
        ...         resolution=Resolution("1080p"),
        ...         is_primary=True,
        ...     )],
        ... )
    """

    # Identity
    id: EpisodeId | None = Field(default=None)

    # Relationship
    series_id: SeriesId
    season_number: int = Field(ge=0)  # 0 for specials
    episode_number: int = Field(ge=1)

    # Content info
    title: Title
    synopsis: str | None = Field(default=None, max_length=10000)
    duration: Duration

    # File variants
    files: list[MediaFile] = Field(default_factory=list)
    thumbnail_path: FilePath | None = None

    # Metadata
    air_date: AirDate | None = None

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | EpisodeId | None) -> EpisodeId | None:
        """Convert string to EpisodeId if needed."""
        if v is None:
            return None
        return EpisodeId(v) if isinstance(v, str) else v


__all__ = ["Episode"]
