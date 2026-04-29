"""Episode entity for TV series."""

from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator

from src.building_blocks.domain import DomainEntity
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    AirDate,
    Duration,
    EpisodeId,
    EpisodeNumber,
    ImageUrl,
    IntroMarker,
    MediaFile,
    SeasonNumber,
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
    season_number: SeasonNumber
    episode_number: EpisodeNumber

    # Content info
    title: Title
    synopsis: str | None = Field(default=None, max_length=10000)
    duration: Duration

    # File variants
    files: list[MediaFile] = Field(default_factory=list)
    thumbnail_path: ImageUrl | None = None
    scrub_preview_path: ImageUrl | None = None

    # Metadata
    air_date: AirDate | None = None

    # Skip-intro support
    intro: IntroMarker | None = None

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | EpisodeId | None) -> EpisodeId | None:
        """Convert string to EpisodeId if needed."""
        if v is None:
            return None
        return EpisodeId(v) if isinstance(v, str) else v

    def with_intro_marker(self, marker: IntroMarker) -> Self:
        """Return a copy with the intro marker set.

        Args:
            marker: The intro marker to attach to this episode.

        Returns:
            A new Episode with the marker applied, or ``self`` if the
            same marker is already in place.

        Raises:
            BusinessRuleViolationException: If ``marker.end_seconds``
                exceeds the episode's duration.
        """
        if marker.end_seconds > self.duration.value:
            raise BusinessRuleViolationException(
                message="Intro end_seconds cannot exceed episode duration",
                rule_code=MediaRuleCodes.INTRO_EXCEEDS_DURATION,
                tags={
                    "episode_duration": self.duration.value,
                    "intro_end_seconds": marker.end_seconds,
                },
            )
        if self.intro == marker:
            return self
        return self.with_updates(intro=marker)

    def with_intro_cleared(self) -> Self:
        """Return a copy with the intro marker removed.

        Returns:
            A new Episode with ``intro`` set to ``None``, or ``self`` if
            it was already absent.
        """
        if self.intro is None:
            return self
        return self.with_updates(intro=None)


__all__ = ["Episode"]
