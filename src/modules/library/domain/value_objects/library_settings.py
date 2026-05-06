"""Library settings value object."""

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.shared_kernel.value_objects.language_code import LanguageCode


class LibrarySettings(CompoundValueObject):
    """Configuration settings for a library's behavior.

    Controls playback preferences, scan behavior, and feature toggles
    for a specific library.

    Attributes:
        preferred_audio_language: Default audio track language.
        preferred_subtitle_language: Default subtitle language, or None to disable.
        subtitle_mode: When to enable subtitles by default.
        generate_thumbnails: Whether to generate video thumbnails during scan.
        detect_intros: Whether to detect intro timestamps for skip feature.
        auto_refresh_metadata: Whether to periodically refresh metadata.

    Example:
        >>> settings = LibrarySettings(
        ...     preferred_audio_language=LanguageCode("ja"),
        ...     preferred_subtitle_language=LanguageCode("en"),
        ...     subtitle_mode=SubtitleMode.ALWAYS,
        ... )
        >>> settings.subtitle_mode
        <SubtitleMode.ALWAYS: 'always'>
    """

    preferred_audio_language: LanguageCode = LanguageCode("en")
    preferred_subtitle_language: LanguageCode | None = None
    subtitle_mode: SubtitleMode = SubtitleMode.FOREIGN_AUDIO_ONLY
    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False

    @classmethod
    def default(cls) -> "LibrarySettings":
        """Create settings with sensible defaults.

        Returns:
            LibrarySettings with English audio, no subtitles by default,
            and thumbnail generation enabled.
        """
        return cls()

    @classmethod
    def for_anime(cls) -> "LibrarySettings":
        """Create settings optimized for anime libraries.

        Returns:
            LibrarySettings with Japanese audio, English subtitles,
            and always-on subtitle mode.
        """
        return cls(
            preferred_audio_language=LanguageCode("ja"),
            preferred_subtitle_language=LanguageCode("en"),
            subtitle_mode=SubtitleMode.ALWAYS,
        )

    @classmethod
    def for_foreign_films(cls, subtitle_language: str = "en") -> "LibrarySettings":
        """Create settings optimized for foreign film libraries.

        Args:
            subtitle_language: Preferred subtitle language code.

        Returns:
            LibrarySettings with foreign audio mode.
        """
        return cls(
            preferred_subtitle_language=LanguageCode(subtitle_language),
            subtitle_mode=SubtitleMode.FOREIGN_AUDIO_ONLY,
        )


__all__ = ["LibrarySettings"]
