"""ServeHlsFileUseCase — resolve a cached HLS file (segment/playlist/VTT)."""

import asyncio
import contextlib
import re
from dataclasses import dataclass
from pathlib import Path

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.stream_dtos import HlsFileOutput
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.ports.now_playing_port import NowPlayingPort
from src.modules.media.application.streaming.playlist_rewriter import (
    SUB_PATH_RE,
    media_type_for,
    rewrite_m3u8,
)

# Matches the ffmpeg segment naming (``segment_0007.ts``) to recover the
# index for the now-playing progress estimate.
_SEGMENT_INDEX_RE = re.compile(r"segment_(\d+)\.ts$")

# Hard cap on how long the use case will park a request waiting for a
# background subtitle extraction. Must comfortably exceed the per-track
# ffmpeg timeout in the HLS adapter so the player gets the .vtt instead
# of a 404 when it picks a slow track right after playback starts.
_SUBTITLE_WAIT_TIMEOUT = 60.0


@dataclass(frozen=True)
class ServeHlsFileInput:
    """Inputs for the HLS file-serving use case.

    Attributes:
        path_hash: Cache key returned by a previous
            ``GenerateHlsPlaylistUseCase`` run.
        relative_path: Path of the requested file inside the cache
            bundle (e.g. ``video/segment_0001.ts``).
        base_url_template: Absolute base URL for the cache entry, used
            to rewrite nested ``.m3u8`` references. Must contain
            ``{parent}`` — the use case substitutes the directory of
            the requested file.
    """

    path_hash: str
    relative_path: str
    base_url_template: str


class ServeHlsFileUseCase:
    """Resolve a cached HLS file, rewriting nested playlists inline."""

    def __init__(
        self,
        hls: HlsPlaylistPort,
        now_playing: NowPlayingPort | None = None,
    ) -> None:
        self._hls = hls
        self._now_playing = now_playing

    async def execute(self, input_dto: ServeHlsFileInput) -> HlsFileOutput:
        """Return the requested file (or rewritten playlist).

        Raises:
            ResourceNotFoundException: When the file is not in the
                cache, or an ``.m3u8`` cannot be read from disk.
        """
        await self._maybe_wait_for_subtitle(input_dto.path_hash, input_dto.relative_path)

        resolved = self._hls.get_file_by_hash(input_dto.path_hash, input_dto.relative_path)
        if resolved is None:
            raise ResourceNotFoundException.for_resource(
                "HlsFile", f"{input_dto.path_hash}/{input_dto.relative_path}"
            )

        if resolved.suffix == ".m3u8":
            return self._build_playlist_output(resolved, input_dto)

        self._note_segment(input_dto.path_hash, resolved, input_dto.relative_path)

        return HlsFileOutput(
            kind="file",
            media_type=media_type_for(input_dto.relative_path),
            path=resolved,
        )

    def _note_segment(self, path_hash: str, resolved: Path, relative_path: str) -> None:
        """Feed the now-playing registry a served ``.ts`` segment.

        Best-effort + observational: byte size for the rolling bitrate
        and the segment index for the progress estimate. Wrapped so a
        bookkeeping error can never fail the segment response.
        """
        if self._now_playing is None or resolved.suffix != ".ts":
            return
        with contextlib.suppress(Exception):
            match = _SEGMENT_INDEX_RE.search(relative_path)
            index = int(match.group(1)) if match else None
            self._now_playing.note_segment(path_hash, resolved.stat().st_size, index)

    async def _maybe_wait_for_subtitle(self, path_hash: str, relative_path: str) -> None:
        """Block on subtitle extraction when the request targets ``sub_<idx>``."""
        sub_match = SUB_PATH_RE.match(relative_path)
        if not sub_match:
            return
        sub_index = int(sub_match.group(1))
        # Offload the blocking Event.wait so we don't pin an event loop
        # thread for tens of seconds while ffmpeg is still demuxing.
        await asyncio.to_thread(
            self._hls.wait_for_subtitle,
            path_hash,
            sub_index,
            _SUBTITLE_WAIT_TIMEOUT,
        )

    @staticmethod
    def _build_playlist_output(resolved: Path, input_dto: ServeHlsFileInput) -> HlsFileOutput:
        """Read an ``.m3u8`` off disk and rewrite its relative references."""
        try:
            content = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise ResourceNotFoundException.for_resource(
                "HlsFile", f"{input_dto.path_hash}/{input_dto.relative_path}"
            ) from exc

        parent_parts = str(Path(input_dto.relative_path).parent)
        base_url = input_dto.base_url_template.format(
            path_hash=input_dto.path_hash,
            parent="" if parent_parts == "." else f"/{parent_parts}",
        )

        return HlsFileOutput(
            kind="playlist",
            media_type=media_type_for(input_dto.relative_path),
            content=rewrite_m3u8(content, base_url),
        )


__all__ = ["ServeHlsFileInput", "ServeHlsFileUseCase"]
