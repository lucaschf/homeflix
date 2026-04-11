"""Video streaming REST API routes.

Uses HLS (HTTP Live Streaming) for all video formats via FFmpeg.
Supports multi-audio and subtitle tracks via master playlist.
Segment endpoints use a path-hash scheme so they never touch the
database — only the initial playlist request needs a DB lookup.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.movie_dtos import GetMovieByIdInput
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.infrastructure.streaming.hls_service import (
    SUB_PATH_RE,
    HlsService,
    media_type_for,
    rewrite_m3u8,
)
from src.modules.media.infrastructure.streaming.media_probe_service import MediaProbeResult

_logger = logging.getLogger(__name__)

# Hard cap on how long the file route will park a request waiting for
# a background subtitle extraction. Must comfortably exceed the per-track
# ffmpeg timeout in HlsService so the player gets the .vtt instead of a
# 404 when it picks a slow track right after playback starts.
_SUBTITLE_WAIT_TIMEOUT = 60.0

router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])


def _resolve_file(file_path: str | None) -> Path:
    """Validate file path exists and return Path object."""
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")
    path = Path(file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    return path


def _serialize_tracks(probe: MediaProbeResult) -> dict[str, list[dict[str, object]]]:
    """Serialize probe result into API response format."""
    return {
        "audio_tracks": [
            {
                "index": t.index,
                "language": t.language.value,
                "codec": t.codec,
                "channels": t.channels,
                "channel_layout": t.channel_layout,
                "title": t.title,
                "is_default": t.is_default,
            }
            for t in probe.audio_tracks
        ],
        "subtitle_tracks": [
            {
                "index": t.index,
                "language": t.language.value,
                "format": t.format,
                "title": t.title,
                "is_default": t.is_default,
                "is_forced": t.is_forced,
                "is_external": t.is_external,
                "is_image_based": t.is_image_based,
            }
            for t in probe.all_subtitles
            if t.is_text_based
        ],
    }


def _serve_master_playlist(hls: HlsService, path_hash: str) -> Response:
    """Read master playlist and rewrite all relative URLs."""
    content = hls.get_master_playlist(path_hash)
    if not content:
        raise HTTPException(status_code=404, detail="Playlist not found")

    base_url = f"/api/v1/stream/hls/{path_hash}"
    return Response(
        content=rewrite_m3u8(content, base_url),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


# -- HLS file serving (no DB access) ------------------------------------------


@router.get("/hls/{path_hash}/{file_path:path}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def hls_file(
    path_hash: str,
    file_path: str,
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> Response:
    """Serve any HLS file (segment, sub-playlist, VTT) by cache hash.

    For .m3u8 files, rewrites relative references to absolute URLs.
    Subtitle requests block on the matching readiness event so the
    player gets the .vtt as soon as ffmpeg finishes extracting it,
    instead of getting an early 404 and giving up. No database access
    needed.
    """
    sub_match = SUB_PATH_RE.match(file_path)
    if sub_match:
        sub_index = int(sub_match.group(1))
        # Offload the blocking Event.wait so we don't pin an event
        # loop thread for tens of seconds while ffmpeg is still
        # demuxing the source container.
        await asyncio.to_thread(hls.wait_for_subtitle, path_hash, sub_index, _SUBTITLE_WAIT_TIMEOUT)

    resolved = hls.get_file_by_hash(path_hash, file_path)
    if not resolved:
        raise HTTPException(status_code=404, detail="File not found")

    if resolved.suffix == ".m3u8":
        try:
            content = resolved.read_text(encoding="utf-8")
        except OSError as e:
            raise HTTPException(status_code=404, detail="Playlist not readable") from e

        parent_parts = str(Path(file_path).parent)
        if parent_parts == ".":
            base_url = f"/api/v1/stream/hls/{path_hash}"
        else:
            base_url = f"/api/v1/stream/hls/{path_hash}/{parent_parts}"

        return Response(
            content=rewrite_m3u8(content, base_url),
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"},
        )

    return FileResponse(
        str(resolved),
        media_type=media_type_for(file_path),
    )


# -- HLS playlist endpoints (need DB to resolve file path) ---------------------


@router.get("/movie/{movie_id}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_hls_playlist(
    movie_id: str,
    start: float = 0.0,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> Response:
    """Generate and serve HLS master playlist for a movie.

    The ``start`` query parameter (default 0) is an optional seek offset
    in seconds. FFmpeg trims the source so the HLS output starts at
    (original time = start), which lets the client resume mid-file
    without waiting for segments to be produced from position 0.
    """
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    file_path = _resolve_file(movie.file_path)
    start_seconds = max(0.0, start)

    try:
        path_hash = await hls.ensure_playlist(str(file_path), start_seconds)
    except Exception as e:
        _logger.exception(
            "HLS generation failed for movie %s (file=%s, start=%ss)",
            movie_id,
            file_path,
            start_seconds,
        )
        detail = str(e) or f"{type(e).__name__}: check server logs"
        raise HTTPException(status_code=500, detail=detail) from e

    return _serve_master_playlist(hls, path_hash)


@router.get("/episode/{series_id}/{season_number}/{episode_number}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_hls_playlist(
    series_id: str,
    season_number: int,
    episode_number: int,
    start: float = 0.0,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> Response:
    """Generate and serve HLS master playlist for an episode.

    The ``start`` query parameter (default 0) is an optional seek offset
    in seconds — same semantics as the movie endpoint.
    """
    file_path = await _find_episode_file(use_case, series_id, season_number, episode_number)
    path = _resolve_file(file_path)
    start_seconds = max(0.0, start)

    try:
        path_hash = await hls.ensure_playlist(str(path), start_seconds)
    except Exception as e:
        _logger.exception(
            "HLS generation failed for episode %s/S%sE%s (file=%s, start=%ss)",
            series_id,
            season_number,
            episode_number,
            path,
            start_seconds,
        )
        detail = str(e) or f"{type(e).__name__}: check server logs"
        raise HTTPException(status_code=500, detail=detail) from e

    return _serve_master_playlist(hls, path_hash)


# -- Track info ----------------------------------------------------------------


@router.get("/movie/{movie_id}/tracks")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_tracks(
    movie_id: str,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> dict[str, list[dict[str, object]]]:
    """Get available audio and subtitle tracks for a movie."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    file_path = _resolve_file(movie.file_path)
    probe = hls.probe_tracks(str(file_path))
    return _serialize_tracks(probe)


@router.get("/episode/{series_id}/{season_number}/{episode_number}/tracks")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_tracks(
    series_id: str,
    season_number: int,
    episode_number: int,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> dict[str, list[dict[str, object]]]:
    """Get available audio and subtitle tracks for an episode."""
    file_path = await _find_episode_file(use_case, series_id, season_number, episode_number)
    path = _resolve_file(file_path)
    probe = hls.probe_tracks(str(path))
    return _serialize_tracks(probe)


# -- Cache management ----------------------------------------------------------


@router.delete("/movie/{movie_id}/hls/cache")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def clear_movie_hls_cache(
    movie_id: str,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    hls: HlsService = Depends(
        Provide[ApplicationContainer.media.hls_service],
    ),
) -> Response:
    """Clear cached HLS segments for a movie, forcing regeneration."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    if movie.file_path:
        hls.clear_cache(movie.file_path)
    return Response(status_code=204)


# -- Direct streaming (fallback for MP4/WebM) ---------------------------------


@router.get("/movie/{movie_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def stream_movie(
    movie_id: str,
    request: Request,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> StreamingResponse:
    """Direct stream a movie file with Range support (MP4/WebM only)."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    path = _resolve_file(movie.file_path)

    return _build_range_response(str(path), path.stat().st_size, request.headers.get("range"))


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
    """Direct stream an episode file with Range support."""
    file_path = await _find_episode_file(use_case, series_id, season_number, episode_number)
    path = _resolve_file(file_path)

    return _build_range_response(str(path), path.stat().st_size, request.headers.get("range"))


# -- Helpers -------------------------------------------------------------------


async def _find_episode_file(
    use_case: GetSeriesByIdUseCase,
    series_id: str,
    season_number: int,
    episode_number: int,
) -> str | None:
    """Find episode file path from series hierarchy."""
    series = await use_case.execute(GetSeriesByIdInput(series_id=series_id))
    for season in series.seasons:
        if season.season_number == season_number:
            for episode in season.episodes:
                if episode.episode_number == episode_number:
                    return episode.file_path
            break
    return None


async def _stream_range(
    file_path: str,
    start: int,
    end: int,
) -> AsyncGenerator[bytes, None]:
    """Stream file bytes in 1MB chunks."""
    chunk_size = 1024 * 1024
    with Path(file_path).open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = f.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _build_range_response(
    file_path: str,
    file_size: int,
    range_header: str | None,
) -> StreamingResponse:
    """Build Range-based streaming response."""
    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        start = max(0, start)
        end = min(end, file_size - 1)

        return StreamingResponse(
            _stream_range(file_path, start, end),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
            },
        )

    return StreamingResponse(
        _stream_range(file_path, 0, file_size - 1),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


__all__ = ["router"]
