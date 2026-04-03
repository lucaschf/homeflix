"""Track selection domain service."""

from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


class TrackSelector:
    """Selects appropriate audio and subtitle tracks based on preferences.

    This domain service encapsulates the logic for choosing the best
    audio and subtitle tracks from available options, considering
    user preferences and library settings.

    Example:
        >>> selector = TrackSelector()
        >>> audio = selector.select_audio(
        ...     tracks=audio_tracks,
        ...     preferred_language=LanguageCode("en"),
        ... )
        >>> subtitle = selector.select_subtitle(
        ...     tracks=subtitle_tracks,
        ...     audio_language=LanguageCode("ja"),
        ...     preferred_language=LanguageCode("en"),
        ...     mode=SubtitleMode.FOREIGN_AUDIO_ONLY,
        ... )
    """

    def select_audio(
        self,
        tracks: list[AudioTrack],
        preferred_language: LanguageCode,
    ) -> AudioTrack | None:
        """Select the best audio track based on preferences.

        Selection priority:
        1. Preferred language with highest channel count
        2. Default track with highest channel count
        3. Track with highest channel count (any language)

        Args:
            tracks: Available audio tracks.
            preferred_language: User's preferred audio language.

        Returns:
            The selected audio track, or None if no tracks available.

        Example:
            >>> tracks = [
            ...     AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
            ...     AudioTrack(index=1, language=LanguageCode("en"), codec="dts", channels=6),
            ... ]
            >>> selector.select_audio(tracks, LanguageCode("en"))
            AudioTrack(index=1, ...)  # 5.1 English track selected
        """
        if not tracks:
            return None

        # Filter tracks by preferred language
        preferred_tracks = [t for t in tracks if t.language.value == preferred_language.value]

        if preferred_tracks:
            # Return the one with most channels
            return max(preferred_tracks, key=lambda t: t.channels)

        # Fallback to default track
        default_tracks = [t for t in tracks if t.is_default]
        if default_tracks:
            return max(default_tracks, key=lambda t: t.channels)

        # Fallback to highest channel count
        return max(tracks, key=lambda t: t.channels)

    def select_subtitle(
        self,
        tracks: list[SubtitleTrack],
        audio_language: LanguageCode,
        preferred_language: LanguageCode,
        mode: SubtitleMode,
    ) -> SubtitleTrack | None:
        """Select a subtitle track based on mode and preferences.

        Behavior by mode:
        - ALWAYS: Returns subtitle in preferred language.
        - FOREIGN_AUDIO_ONLY: Returns subtitle only if audio != preferred language.
        - FORCED_ONLY: Returns forced subtitle if available.
        - NONE: Returns None.

        Args:
            tracks: Available subtitle tracks.
            audio_language: Language of the selected audio track.
            preferred_language: User's preferred subtitle language.
            mode: Subtitle display mode.

        Returns:
            The selected subtitle track, or None based on mode/availability.

        Example:
            >>> subtitles = [
            ...     SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
            ...     SubtitleTrack(index=1, language=LanguageCode("pt"), format="srt"),
            ... ]
            >>> selector.select_subtitle(
            ...     tracks=subtitles,
            ...     audio_language=LanguageCode("ja"),
            ...     preferred_language=LanguageCode("en"),
            ...     mode=SubtitleMode.FOREIGN_AUDIO_ONLY,
            ... )
            SubtitleTrack(index=0, ...)  # English subtitle for Japanese audio
        """
        if not tracks or mode == SubtitleMode.NONE:
            return None

        if mode == SubtitleMode.FORCED_ONLY:
            return self._select_forced_subtitle(tracks, preferred_language)

        if (
            mode == SubtitleMode.FOREIGN_AUDIO_ONLY
            and audio_language.value == preferred_language.value
        ):
            # Only show subtitles if audio is not in preferred language
            return None

        # ALWAYS mode or FOREIGN_AUDIO_ONLY with foreign audio
        return self._select_by_language(tracks, preferred_language)

    def _select_forced_subtitle(
        self,
        tracks: list[SubtitleTrack],
        preferred_language: LanguageCode,
    ) -> SubtitleTrack | None:
        """Select a forced subtitle track.

        Args:
            tracks: Available subtitle tracks.
            preferred_language: User's preferred subtitle language.

        Returns:
            A forced subtitle track in preferred language, or any forced track.
        """
        forced_tracks = [t for t in tracks if t.is_forced]

        if not forced_tracks:
            return None

        # Prefer forced track in user's language
        preferred_forced = [
            t for t in forced_tracks if t.language.value == preferred_language.value
        ]

        if preferred_forced:
            return preferred_forced[0]

        return forced_tracks[0]

    def _select_by_language(
        self,
        tracks: list[SubtitleTrack],
        preferred_language: LanguageCode,
    ) -> SubtitleTrack | None:
        """Select subtitle by language preference.

        Priority:
        1. Preferred language, non-forced, text-based
        2. Preferred language, non-forced
        3. Default track
        4. First available

        Args:
            tracks: Available subtitle tracks.
            preferred_language: User's preferred subtitle language.

        Returns:
            The best matching subtitle track.
        """
        # Filter by preferred language
        preferred_tracks = [
            t for t in tracks if t.language.value == preferred_language.value and not t.is_forced
        ]

        if preferred_tracks:
            # Prefer text-based over image-based
            text_tracks = [t for t in preferred_tracks if t.is_text_based]
            if text_tracks:
                return text_tracks[0]
            return preferred_tracks[0]

        # Fallback to default track
        default_tracks = [t for t in tracks if t.is_default and not t.is_forced]
        if default_tracks:
            return default_tracks[0]

        # Fallback to first non-forced track
        non_forced = [t for t in tracks if not t.is_forced]
        if non_forced:
            return non_forced[0]

        return tracks[0] if tracks else None


__all__ = ["TrackSelector"]
