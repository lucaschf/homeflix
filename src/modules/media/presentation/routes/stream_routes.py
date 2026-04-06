"""Video streaming REST API routes.

Uses HLS (HTTP Live Streaming) for all video formats via FFmpeg.
Segments are cached for subsequent plays. MP4/WebM also support
direct Range-based streaming as fallback.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.movie_dtos import GetMovieByIdInput
from src.modules.media.application.dtos.series_dtos import GetSeriesByIdInput
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.infrastructure.streaming.hls_service import HlsService

router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])

_hls = HlsService()


def _resolve_file(file_path: str | None) -> Path:
    """Validate file path exists and return Path object."""
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")
    path = Path(file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    return path


# ── HLS endpoints ────────────────────────────────────────────


@router.get("/movie/{movie_id}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_hls_playlist(
    movie_id: str,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> FileResponse:
    """Generate and serve HLS playlist for a movie."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    path = _resolve_file(movie.file_path)

    try:
        playlist = _hls.generate(str(path))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return FileResponse(
        str(playlist),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/movie/{movie_id}/hls/{segment}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_hls_segment(
    movie_id: str,
    segment: str,
    use_case: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> FileResponse:
    """Serve an HLS segment file."""
    movie = await use_case.execute(GetMovieByIdInput(movie_id=movie_id))
    path = _resolve_file(movie.file_path)

    segment_path = _hls.get_segment_path(str(path), segment)
    if not segment_path:
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(str(segment_path), media_type="video/mp2t")


@router.get("/episode/{series_id}/{season_number}/{episode_number}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_hls_playlist(
    series_id: str,
    season_number: int,
    episode_number: int,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> FileResponse:
    """Generate and serve HLS playlist for an episode."""
    file_path = await _find_episode_file(use_case, series_id, season_number, episode_number)
    path = _resolve_file(file_path)

    try:
        playlist = _hls.generate(str(path))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return FileResponse(
        str(playlist),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/episode/{series_id}/{season_number}/{episode_number}/hls/{segment}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_hls_segment(
    series_id: str,
    season_number: int,
    episode_number: int,
    segment: str,
    use_case: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> FileResponse:
    """Serve an HLS segment file for an episode."""
    file_path = await _find_episode_file(use_case, series_id, season_number, episode_number)
    path = _resolve_file(file_path)

    segment_path = _hls.get_segment_path(str(path), segment)
    if not segment_path:
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(str(segment_path), media_type="video/mp2t")


# ── Direct streaming (fallback for MP4/WebM) ────────────────


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


# ── Helpers ──────────────────────────────────────────────────


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
