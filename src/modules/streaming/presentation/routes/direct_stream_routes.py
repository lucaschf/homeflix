"""Direct byte-range streaming routes (MP4/WebM fallback).

The HLS path is the primary player; these endpoints serve the raw file
with HTTP Range support for containers the browser can play directly.

The routes resolve a media id to a physical file path through the
:class:`MediaPlaybackLookupPort` ACL (never importing the catalog
aggregates) and hand the primitive path to the pure
:class:`StreamFileRangeUseCase`.
"""

from pathlib import Path

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import resolve_profile_id
from src.modules.streaming.application.ports.media_lookup_port import (
    MediaPlaybackLookupPort,
)
from src.modules.streaming.application.use_cases.stream_file_range import (
    StreamFileRangeInput,
    StreamFileRangeUseCase,
)

router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])


def _require_file(file_path: str | None) -> str:
    """Validate that a file was resolved and exists on disk, or 404.

    Missing DB metadata and a stale/removed file on disk both map to
    ``404`` here — the streaming use case downstream can assume the path
    is reachable.
    """
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")
    if not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    return file_path


async def _stream_range(
    use_case: StreamFileRangeUseCase,
    file_path: str,
    range_header: str | None,
) -> StreamingResponse:
    """Run the range-streaming use case and build a StreamingResponse."""
    output = await use_case.execute(
        StreamFileRangeInput(file_path=file_path, range_header=range_header),
    )
    return StreamingResponse(
        output.body,
        status_code=output.status_code,
        media_type=output.media_type,
        headers=output.headers,
    )


@router.get("/movie/{movie_id}")
@inject
async def stream_movie(
    movie_id: str,
    request: Request,
    profile_id: str = Depends(resolve_profile_id),
    media_lookup: MediaPlaybackLookupPort = Depends(
        Provide[ApplicationContainer.streaming.media_playback_lookup],
    ),
    stream_uc: StreamFileRangeUseCase = Depends(
        Provide[ApplicationContainer.streaming.stream_file_range],
    ),
) -> StreamingResponse:
    """Direct stream a movie file with Range support (MP4/WebM only)."""
    movie = await media_lookup.find_movie(profile_id, movie_id)
    file_path = _require_file(movie.file_path)
    return await _stream_range(stream_uc, file_path, request.headers.get("range"))


@router.get("/episode/{series_id}/{season_number}/{episode_number}")
@inject
async def stream_episode(
    series_id: str,
    season_number: int,
    episode_number: int,
    request: Request,
    profile_id: str = Depends(resolve_profile_id),
    media_lookup: MediaPlaybackLookupPort = Depends(
        Provide[ApplicationContainer.streaming.media_playback_lookup],
    ),
    stream_uc: StreamFileRangeUseCase = Depends(
        Provide[ApplicationContainer.streaming.stream_file_range],
    ),
) -> StreamingResponse:
    """Direct stream an episode file with Range support."""
    episode = await media_lookup.find_episode(profile_id, series_id, season_number, episode_number)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    file_path = _require_file(episode.file_path)
    return await _stream_range(stream_uc, file_path, request.headers.get("range"))


__all__ = ["router"]
