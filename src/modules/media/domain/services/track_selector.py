"""Track selection domain service (ADR-005).

Owns the rule for *which* audio track is the default, so the probe can
report tracks truthfully (only the container's declared default) instead
of fabricating one. The decision is made at read time from the tracks plus
the caller's preference, not baked into the persisted data.

Only :meth:`select_audio` exists today — that is the rule Card B needs. The
subtitle-by-mode selection ADR-005 also sketches has no consumer yet (the
probe never fabricates a subtitle default), so it is deferred until one
appears.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.shared_kernel.value_objects.language_code import LanguageCode
    from src.shared_kernel.value_objects.tracks import AudioTrack


class TrackSelector:
    """Selects appropriate tracks based on preferences (ADR-005)."""

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
            preferred_language: The library's preferred audio language, or
                ``None`` when no preference is available (e.g. at a
                library-agnostic boundary).

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


__all__ = ["TrackSelector"]
