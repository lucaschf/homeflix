"""ClearHlsCacheUseCase — drop every cache entry tied to a media file."""

from dataclasses import dataclass

from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort


@dataclass(frozen=True)
class ClearHlsCacheInput:
    """Inputs for the HLS cache-clearing use case.

    Attributes:
        file_path: Absolute path of the media file whose cache should
            be discarded. A ``None`` value is tolerated so routes that
            read the path from a (possibly missing) lookup can skip
            the call without branching.
    """

    file_path: str | None


class ClearHlsCacheUseCase:
    """Invalidate every cache bucket for a given source file."""

    def __init__(self, hls: HlsPlaylistPort) -> None:
        self._hls = hls

    async def execute(self, input_dto: ClearHlsCacheInput) -> None:
        """Clear the cache; no-op when ``file_path`` is ``None``."""
        if input_dto.file_path:
            self._hls.clear_cache(input_dto.file_path)


__all__ = ["ClearHlsCacheInput", "ClearHlsCacheUseCase"]
