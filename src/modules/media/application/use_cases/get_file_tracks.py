"""GetFileTracksUseCase — probe a media file and serialize its tracks."""

from dataclasses import dataclass

from src.modules.media.application.dtos.stream_dtos import (
    TrackListOutput,
    serialize_tracks,
)
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.ports.profile_playback_preference_port import (
    ProfilePlaybackPreferencePort,
)


@dataclass(frozen=True)
class GetFileTracksInput:
    """Inputs required to probe and serialize tracks.

    Attributes:
        file_path: Absolute path to the source video file.
        profile_id: External id (``prf_xxx``) of the viewing profile, used
            to resolve its preferred audio language for the default-audio
            choice (ADR-026). ``None`` skips the preference (container
            default wins).
    """

    file_path: str
    profile_id: str | None = None


class GetFileTracksUseCase:
    """Return the audio and text subtitle tracks a player can select.

    Resolves the viewing profile's preferred audio language (ADR-026) via a
    cross-BC read port to the Preferences BC, and applies it to the
    default-audio choice. The probe still reports ``is_default`` truthfully;
    the preference only steers which track this projection marks as default.
    """

    def __init__(
        self,
        hls: HlsPlaylistPort,
        playback_preference: ProfilePlaybackPreferencePort,
    ) -> None:
        self._hls = hls
        self._playback_preference = playback_preference

    async def execute(self, input_dto: GetFileTracksInput) -> TrackListOutput:
        """Probe ``file_path`` (using the cache when available) and project."""
        probe = self._hls.probe_tracks(input_dto.file_path)
        preferred_audio_language = None
        if input_dto.profile_id is not None:
            preference = await self._playback_preference.for_profile(input_dto.profile_id)
            preferred_audio_language = preference.audio_language
        return serialize_tracks(probe, preferred_audio_language)


__all__ = ["GetFileTracksInput", "GetFileTracksUseCase"]
