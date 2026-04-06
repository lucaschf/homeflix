"""Video streaming REST API routes.

Supports direct streaming for MP4/WebM and FFmpeg transmuxing
for MKV/AVI/MOV/WMV to MP4 (container conversion without
re-encoding for browser compatibility).
"""

import asyncio
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.movie_dtos import GetMovieByIdInput
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase

router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])

_CHUNK_SIZE = 64 * 1024  # 64 KB for transmuxed streams

# Formats that browsers can play natively
_NATIVE_FORMATS = {".mp4", ".webm"}


def _needs_transmux(file_path: str) -> bool:
    """Check if file needs FFmpeg transmuxing for browser playback."""
    return Path(file_path).suffix.lower() not in _NATIVE_FORMATS


def _ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


async def _stream_native(
    file_path: str,
    start: int,
    end: int,
) -> AsyncGenerator[bytes, None]:
    """Stream native file bytes in chunks."""
    with Path(file_path).open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        chunk_size = 1024 * 1024  # 1 MB for native
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


async def _stream_transmux(file_path: str) -> AsyncGenerator[bytes, None]:
    """Transmux video to MP4 via FFmpeg (copy codecs, no re-encoding)."""
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-c:v",
        "copy",
        "-c:a",
        "aac",  # Re-encode audio to AAC for browser compat
        "-movflags",
        "frag_keyframe+empty_moov+faststart",
        "-f",
        "mp4",
        "-loglevel",
        "error",
        "pipe:1",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        assert process.stdout is not None
        while True:
            chunk = await process.stdout.read(_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


def _resolve_file(file_path: str | None) -> Path:
    """Validate file path exists and return Path object."""
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")

    path = Path(file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    return path


def _build_response(
    file_path: str,
    file_size: int,
    range_header: str | None,
) -> StreamingResponse:
    """Build streaming response — native with Range or transmuxed."""
    if _needs_transmux(file_path):
        if not _ffmpeg_available():
            raise HTTPException(
                status_code=500,
                detail="FFmpeg is required to stream MKV/AVI files but was not found",
            )
        # Transmuxed streams don't support Range (live pipe)
        return StreamingResponse(
            _stream_transmux(file_path),
            media_type="video/mp4",
            headers={"Accept-Ranges": "none"},
        )

    # Native MP4/WebM — support Range requests
    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        start = max(0, start)
        end = min(end, file_size - 1)
        content_length = end - start + 1

        return StreamingResponse(
            _stream_native(file_path, start, end),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    return StreamingResponse(
        _stream_native(file_path, 0, file_size - 1),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@router.get("/movie/{movie_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def stream_movie(
    movie_id: str,
    request: Request,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> StreamingResponse:
    """Stream a movie's primary video file."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    path = _resolve_file(movie.file_path)

    return _build_response(
        str(path),
        path.stat().st_size,
        request.headers.get("range"),
    )


@router.get("/episode/{series_id}/{season_number}/{episode_number}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def stream_episode(
    series_id: str,
    season_number: int,
    episode_number: int,
    request: Request,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> StreamingResponse:
    """Stream an episode's primary video file."""
    series = await use_case.execute(GetSeriesByIdInput(series_id=series_id))

    file_path = None
    for season in series.seasons:
        if season.season_number == season_number:
            for episode in season.episodes:
                if episode.episode_number == episode_number:
                    file_path = episode.file_path
                    break
            break

    path = _resolve_file(file_path)

    return _build_response(
        str(path),
        path.stat().st_size,
        request.headers.get("range"),
    )


__all__ = ["router"]
