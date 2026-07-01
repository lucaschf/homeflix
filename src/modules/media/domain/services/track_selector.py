"""Track selection domain service (ADR-005 / ADR-026).

Owns the rule for *which* audio and subtitle track is the default, so the
probe can report tracks truthfully (only the container's declared default)
instead of fabricating one. The decision is made at read time from the
tracks plus the viewing profile's preference, not baked into the persisted
data — the server is the authority (ADR-026).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.shared_kernel.value_objects.subtitle_mode import SubtitleMode

if TYPE_CHECKING:
    from src.shared_kernel.value_objects.language_code import LanguageCode
    from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


class TrackSelector:
    """Selects appropriate tracks based on preferences (ADR-005 / ADR-026)."""

    def select_audio(
        self,
        tracks: list[AudioTrack],
        preferred_language: LanguageCode | None = None,
    ) -> AudioTrack | None:
        """Pick the default audio track for a file.

        Priority (ADR-005):

        1. A track in the preferred language, choosing the one with the
           most channels.
        2. The track the container declares default.
        3. The first track.

        Args:
            tracks: The file's audio tracks, in container order.
            preferred_language: The viewing profile's preferred audio
                language (ADR-026), or ``None`` when no preference is
                available (e.g. at a profile-agnostic boundary).

        Returns:
            The selected track, or ``None`` when there are no audio tracks.
        """
        if not tracks:
            return None

        if preferred_language is not None:
            in_language = [t for t in tracks if t.language == preferred_language]
            if in_language:
                return max(in_language, key=lambda t: t.channels)

        return next((t for t in tracks if t.is_default), tracks[0])

    def select_subtitle(
        self,
        subtitles: list[SubtitleTrack],
        audio_language: LanguageCode | None,
        preferred_language: LanguageCode | None,
        mode: SubtitleMode,
    ) -> SubtitleTrack | None:
        """Pick the default subtitle track for a file (ADR-005 / ADR-026).

        Behavior per ``mode``:

        - ``OFF``: never auto-enable a subtitle.
        - ``FORCED_ONLY``: the first forced subtitle (on-screen signs /
          foreign lines), regardless of language; ``None`` if none is forced.
          Intentionally independent of ``preferred_language`` — forced signs
          should show whatever the language preference is (ADR-026).
        - ``ALWAYS``: a subtitle in ``preferred_language``.
        - ``FOREIGN_ONLY``: a subtitle in ``preferred_language``, but only
          when the chosen audio is *not* already in that language (i.e. the
          viewer is watching foreign-language audio). An unknown audio
          language (``None``) is treated as foreign, so the subtitle shows.

        ``subtitles`` should be the selectable (text) tracks — image-based
        subtitles can't be served as WebVTT, so they are never defaulted.

        Args:
            subtitles: The file's selectable subtitle tracks, in order.
            audio_language: Language of the audio track that was selected
                (needed by ``FOREIGN_ONLY``), or ``None``.
            preferred_language: The profile's preferred subtitle language,
                or ``None`` when unavailable.
            mode: The profile's subtitle mode.

        Returns:
            The subtitle to mark default, or ``None`` when none applies.
        """
        if not subtitles or mode is SubtitleMode.OFF:
            return None

        if mode is SubtitleMode.FORCED_ONLY:
            return next((s for s in subtitles if s.is_forced), None)

        if preferred_language is None:
            return None

        in_language = next((s for s in subtitles if s.language == preferred_language), None)
        # ALWAYS shows the preferred-language subtitle; FOREIGN_ONLY shows it
        # only when the chosen audio is not already in that language.
        show = mode is SubtitleMode.ALWAYS or (
            mode is SubtitleMode.FOREIGN_ONLY and audio_language != preferred_language
        )
        return in_language if show else None


__all__ = ["TrackSelector"]
