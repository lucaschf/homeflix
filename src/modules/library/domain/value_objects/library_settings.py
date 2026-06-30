"""Library settings value object."""

from src.building_blocks.domain.value_objects import CompoundValueObject


class LibrarySettings(CompoundValueObject):
    """Configuration settings for a library's scan behavior and feature toggles.

    Playback preferences (audio/subtitle language and subtitle mode) are
    *not* here: per ADR-026 they are per-user in the Preferences BC, not
    per-library. This value object holds only library-scoped scan/processing
    toggles.

    Attributes:
        generate_thumbnails: Whether to generate video thumbnails during scan.
        detect_intros: Whether to detect intro timestamps for skip feature.
        auto_refresh_metadata: Whether to periodically refresh metadata.

    Example:
        >>> settings = LibrarySettings(detect_intros=True)
        >>> settings.generate_thumbnails
        True
    """

    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False

    @classmethod
    def default(cls) -> "LibrarySettings":
        """Create settings with sensible defaults.

        Returns:
            LibrarySettings with thumbnail generation enabled and the
            other scan toggles off.
        """
        return cls()


__all__ = ["LibrarySettings"]
