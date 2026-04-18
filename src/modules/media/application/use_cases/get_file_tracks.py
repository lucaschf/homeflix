"""GetFileTracksUseCase — probe a media file and serialize its tracks."""

from dataclasses import dataclass

from src.modules.media.application.dtos.stream_dtos import (
    TrackListOutput,
    serialize_tracks,
)
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort


@dataclass(frozen=True)
class GetFileTracksInput:
    """Inputs required to probe and serialize tracks.

    Attributes:
        file_path: Absolute path to the source video file.
    """

    file_path: str


class GetFileTracksUseCase:
    """Return the audio and text subtitle tracks a player can select."""

    def __init__(self, hls: HlsPlaylistPort) -> None:
        self._hls = hls

    async def execute(self, input_dto: GetFileTracksInput) -> TrackListOutput:
        """Probe ``file_path`` (using the cache when available) and project."""
        probe = self._hls.probe_tracks(input_dto.file_path)
        return serialize_tracks(probe)


__all__ = ["GetFileTracksInput", "GetFileTracksUseCase"]
