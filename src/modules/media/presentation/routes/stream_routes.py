"""Video streaming REST API routes."""

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

_CHUNK_SIZE = 1024 * 1024  # 1 MB

_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".wmv": "video/x-ms-wmv",
    ".webm": "video/webm",
}


def _get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension."""
    ext = Path(file_path).suffix.lower()
    return _MIME_TYPES.get(ext, "application/octet-stream")


async def _stream_file(
    file_path: str,
    start: int,
    end: int,
) -> AsyncGenerator[bytes, None]:
    """Stream file bytes in chunks."""
    with Path(file_path).open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk_size = min(_CHUNK_SIZE, remaining)
            data = f.read(chunk_size)
            if not data:
                break
            remaining -= len(data)
            yield data


def _build_range_response(
    file_path: str,
    file_size: int,
    range_header: str | None,
) -> StreamingResponse:
    """Build a streaming response with Range support."""
    content_type = _get_mime_type(file_path)

    if range_header:
        # Parse Range header: "bytes=start-end"
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")

        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1

        start = max(0, start)
        end = min(end, file_size - 1)
        content_length = end - start + 1

        return StreamingResponse(
            _stream_file(file_path, start, end),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    return StreamingResponse(
        _stream_file(file_path, 0, file_size - 1),
        media_type=content_type,
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

    if not movie.file_path:
        raise HTTPException(status_code=404, detail="No video file available")

    path = Path(movie.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    return _build_range_response(movie.file_path, file_size, range_header)


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

    if not file_path:
        raise HTTPException(status_code=404, detail="Episode file not found")

    path = Path(file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    return _build_range_response(file_path, file_size, range_header)


__all__ = ["router"]
