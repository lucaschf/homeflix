"""Episode entity for TV series."""

from __future__ import annotations

from datetime import date  # noqa: TCH003 - Pydantic needs this at runtime
from typing import Self

from pydantic import Field, field_validator

from src.domain.media.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeriesId,
    Title,
)
from src.domain.shared.models import DomainEntity


class Episode(DomainEntity[EpisodeId]):
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
    air_date: date | None = None

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | EpisodeId | None) -> EpisodeId | None:
        """Convert string to EpisodeId if needed."""
        if v is None:
            return None
        return EpisodeId(v) if isinstance(v, str) else v

    # ── file variant helpers ──────────────────────────────────────────

    @property
    def primary_file(self) -> MediaFile | None:
        """Return the primary file variant, if any."""
        return next((f for f in self.files if f.is_primary), None)

    @property
    def best_file(self) -> MediaFile | None:
        """Return the highest-resolution file variant."""
        if not self.files:
            return None
        return max(self.files, key=lambda f: f.resolution.total_pixels)

    @property
    def available_resolutions(self) -> list[Resolution]:
        """Return resolutions sorted highest-first."""
        return sorted(
            [f.resolution for f in self.files],
            key=lambda r: r.total_pixels,
            reverse=True,
        )

    @property
    def total_size(self) -> int:
        """Return total file size across all variants."""
        return sum(f.file_size for f in self.files)

    def with_file(self, file: MediaFile) -> Self:
        """Add a file variant. No-op if same file_path exists.

        Args:
            file: The file variant to add.

        Returns:
            A new Episode with the file added, or self if duplicate path.
        """
        if any(f.file_path == file.file_path for f in self.files):
            return self
        return self.with_updates(files=[*self.files, file])

    def get_file_by_resolution(self, resolution: Resolution | str) -> MediaFile | None:
        """Find a file variant by resolution.

        Args:
            resolution: The resolution to search for (string or Resolution).

        Returns:
            The matching MediaFile, or None.
        """
        if isinstance(resolution, str):
            resolution = Resolution(resolution)
        return next(
            (f for f in self.files if f.resolution == resolution),
            None,
        )


__all__ = ["Episode"]
