"""GenerateHlsPlaylistUseCase — build (or reuse) the HLS master playlist."""

from dataclasses import dataclass

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.stream_dtos import HlsPlaylistOutput
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.streaming.playlist_rewriter import rewrite_m3u8


@dataclass(frozen=True)
class GenerateHlsPlaylistInput:
    """Inputs required to prepare an HLS master playlist.

    Attributes:
        file_path: Absolute path to the source video file.
        base_url_template: ``str.format``-style template the use case
            resolves against the generated cache hash to produce the
            absolute URL that prefixes every relative reference inside
            the rewritten playlist. Must contain ``{path_hash}`` —
            e.g. ``"/api/v1/stream/hls/{path_hash}"``. The use case
            does not know its own mount point, so presentation passes
            it in.
        start_seconds: Optional resume offset (see
            ``HlsPlaylistPort.ensure_playlist``).
    """

    file_path: str
    base_url_template: str
    start_seconds: float = 0.0


class GenerateHlsPlaylistUseCase:
    """Ensure the HLS cache is warm and return a ready-to-serve m3u8."""

    def __init__(self, hls: HlsPlaylistPort) -> None:
        self._hls = hls

    async def execute(self, input_dto: GenerateHlsPlaylistInput) -> HlsPlaylistOutput:
        """Generate (or reuse) the cache and return the rewritten master playlist.

        Args:
            input_dto: File path, base URL, and optional seek.

        Returns:
            Path hash and rewritten master m3u8 content.

        Raises:
            ResourceNotFoundException: If the playlist content is missing
                from the cache after ``ensure_playlist`` returns.
        """
        start = max(0.0, input_dto.start_seconds)
        path_hash = await self._hls.ensure_playlist(input_dto.file_path, start)

        content = self._hls.get_master_playlist(path_hash)
        if content is None:
            raise ResourceNotFoundException.for_resource("HlsMasterPlaylist", path_hash)

        base_url = input_dto.base_url_template.format(path_hash=path_hash)
        return HlsPlaylistOutput(
            path_hash=path_hash,
            rewritten_content=rewrite_m3u8(content, base_url),
        )


__all__ = ["GenerateHlsPlaylistInput", "GenerateHlsPlaylistUseCase"]
