"""Mixin for entities that have file variants (Movie, Episode)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from src.modules.media.domain.value_objects import MediaFile, Resolution
    from src.shared_kernel.value_objects.language_code import LanguageCode


class FileVariantMixin:
    """Shared file variant helpers for entities with a ``files`` field.

    Provides properties and methods for querying and managing the list
    of :class:`MediaFile` variants attached to an entity.

    Subclasses must define a ``files: list[MediaFile]`` attribute and
    a ``with_updates(**kwargs) -> Self`` method (provided by DomainEntity).
    """

    files: list[MediaFile]

    if TYPE_CHECKING:

        def with_updates(self, **changes: Any) -> Self:
            """Return a copy with fields replaced (provided by DomainModel)."""
            ...

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
    def has_hdr(self) -> bool:
        """Whether any file variant carries an HDR format.

        Returns:
            True when at least one variant was probed with an HDR
            format (HDR10, Dolby Vision, ...).
        """
        return any(f.hdr_format is not None for f in self.files)

    @property
    def audio_languages(self) -> frozenset[LanguageCode]:
        """Every audio language across the file variants.

        The union, not the intersection: the title can be watched in a
        language as soon as any variant carries it. A track probed
        without a language tag reports the prober's undetermined code,
        which stays in the set so a caller can tell "unknown" from
        "absent".

        Returns:
            The distinct audio track languages, empty when no variant
            has been probed.
        """
        return frozenset(track.language for f in self.files for track in f.audio_tracks)

    @property
    def total_size(self) -> int:
        """Return total file size across all variants."""
        return sum(f.file_size for f in self.files)

    def with_file(self, file: MediaFile) -> Self:
        """Add a file variant. No-op if same file_path exists.

        Args:
            file: The file variant to add.

        Returns:
            A new instance with the file added, or self if duplicate path.
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
        from src.modules.media.domain.value_objects import Resolution as Res

        if isinstance(resolution, str):
            resolution = Res(resolution)
        return next(
            (f for f in self.files if f.resolution == resolution),
            None,
        )


__all__ = ["FileVariantMixin"]
