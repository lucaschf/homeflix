"""Video streaming REST API routes.

Uses HLS (HTTP Live Streaming) for all video formats via FFmpeg.
Supports multi-audio and subtitle tracks via master playlist.
Segment endpoints use a path-hash scheme so they never touch the
database — only the initial playlist request needs a DB lookup.

Routes stay thin: look up the movie/episode, hand the file path to
the streaming use cases, and map the DTO they return into the right
FastAPI response.
"""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from src.building_blocks.application.errors import ResourceNotFoundException
from src.config.containers import ApplicationContainer
from src.infrastructure.scheduling import ThumbnailBackfillJob
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.application.dtos.movie_dtos import GetMovieByIdInput
from src.modules.media.application.dtos.series_dtos import EpisodeOutput, GetSeriesByIdInput
from src.modules.media.application.use_cases.clear_hls_cache import (
    ClearHlsCacheInput,
    ClearHlsCacheUseCase,
)
from src.modules.media.application.use_cases.generate_hls_playlist import (
    GenerateHlsPlaylistInput,
    GenerateHlsPlaylistUseCase,
)
from src.modules.media.application.use_cases.get_file_tracks import (
    GetFileTracksInput,
    GetFileTracksUseCase,
)
from src.modules.media.application.use_cases.get_movie_by_id import GetMovieByIdUseCase
from src.modules.media.application.use_cases.get_series_by_id import GetSeriesByIdUseCase
from src.modules.media.application.use_cases.serve_hls_file import (
    ServeHlsFileInput,
    ServeHlsFileUseCase,
)
from src.modules.media.application.use_cases.stream_file_range import (
    StreamFileRangeInput,
    StreamFileRangeUseCase,
)
from src.modules.media.presentation.dependencies import resolve_profile_id

router = APIRouter(prefix="/api/v1/stream", tags=["Streaming"])

# Base-URL templates consumed by the stream use cases. The use cases
# don't know where they're mounted, so the router injects them.
_MASTER_BASE_URL = "/api/v1/stream/hls/{path_hash}"
_FILE_BASE_URL = "/api/v1/stream/hls/{path_hash}{parent}"

# Strong refs for fire-and-forget eager scrub-preview generation.
# ``asyncio.create_task`` returns a Task that the loop only weakly
# references; without holding it here a brief GC could cancel an
# in-flight ffmpeg run before it completes.
_eager_thumbnail_tasks: set[asyncio.Task[bool]] = set()


def _fire_eager_movie(job: ThumbnailBackfillJob, movie_id: str) -> None:
    task = asyncio.create_task(job.process_movie_by_id(movie_id))
    _eager_thumbnail_tasks.add(task)
    task.add_done_callback(_eager_thumbnail_tasks.discard)


def _fire_eager_episode(job: ThumbnailBackfillJob, episode_id: str) -> None:
    task = asyncio.create_task(job.process_episode_by_id(episode_id))
    _eager_thumbnail_tasks.add(task)
    task.add_done_callback(_eager_thumbnail_tasks.discard)


def _require_file(file_path: str | None) -> str:
    """Validate that a file was resolved and exists on disk, or 404.

    Mirrors the pre-refactor behaviour: missing DB metadata and a
    stale/removed file on disk both map to ``404`` here — the
    streaming use cases downstream can assume the path is reachable.
    """
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")
    if not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    return file_path


# -- HLS file serving (no DB access) ------------------------------------------


@router.get("/hls/{path_hash}/{file_path:path}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def hls_file(
    path_hash: str,
    file_path: str,
    use_case: ServeHlsFileUseCase = Depends(
        Provide[ApplicationContainer.media.serve_hls_file],
    ),
) -> Response:
    """Serve any HLS file (segment, sub-playlist, VTT) by cache hash."""
    try:
        output = await use_case.execute(
            ServeHlsFileInput(
                path_hash=path_hash,
                relative_path=file_path,
                base_url_template=_FILE_BASE_URL,
            )
        )
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    if output.kind == "playlist":
        return Response(
            content=output.content,
            media_type=output.media_type,
            headers={"Cache-Control": "no-cache"},
        )
    if output.path is None:
        raise RuntimeError(
            f"ServeHlsFile returned non-playlist output without a path (kind={output.kind!r})"
        )
    return FileResponse(str(output.path), media_type=output.media_type)


# -- HLS playlist endpoints (need DB to resolve file path) ---------------------


@router.get("/movie/{movie_id}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_hls_playlist(
    movie_id: str,
    start: int = Query(
        0,
        ge=0,
        description=(
            "Source-time second to begin transcoding at, honoured "
            "exactly so a forward seek starts a fresh encode at the "
            "target. Defaults to 0 for legacy single-bucket caching."
        ),
    ),
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    hls_uc: GenerateHlsPlaylistUseCase = Depends(
        Provide[ApplicationContainer.media.generate_hls_playlist],
    ),
    backfill_job: ThumbnailBackfillJob = Depends(
        Provide[ApplicationContainer.thumbnail_backfill_job],
    ),
) -> Response:
    """Generate and serve HLS master playlist for a movie.

    When the movie has no scrub-preview yet, fires an eager backfill
    in the background so a freshly-imported file gets thumbnails
    without waiting for the next periodic tick.
    """
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    file_path = _require_file(movie.file_path)
    if movie.scrub_preview_path is None:
        _fire_eager_movie(backfill_job, movie_id)
    return await _serve_master(hls_uc, file_path, start=start)


@router.get("/episode/{series_id}/{season_number}/{episode_number}/hls/playlist.m3u8")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_hls_playlist(
    series_id: str,
    season_number: int,
    episode_number: int,
    start: int = Query(
        0,
        ge=0,
        description=(
            "Source-time second to begin transcoding at, honoured "
            "exactly so a forward seek starts a fresh encode at the "
            "target. Defaults to 0 for legacy single-bucket caching."
        ),
    ),
    profile_id: str = Depends(resolve_profile_id),
    series_uc: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
    hls_uc: GenerateHlsPlaylistUseCase = Depends(
        Provide[ApplicationContainer.media.generate_hls_playlist],
    ),
    backfill_job: ThumbnailBackfillJob = Depends(
        Provide[ApplicationContainer.thumbnail_backfill_job],
    ),
) -> Response:
    """Generate and serve HLS master playlist for an episode."""
    episode = await _find_episode(series_uc, profile_id, series_id, season_number, episode_number)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    file_path = _require_file(episode.file_path)
    if episode.scrub_preview_path is None and episode.id is not None:
        _fire_eager_episode(backfill_job, episode.id)
    return await _serve_master(hls_uc, file_path, start=start)


# -- Track info ----------------------------------------------------------------


@router.get("/movie/{movie_id}/tracks")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_tracks(
    movie_id: str,
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    tracks_uc: GetFileTracksUseCase = Depends(
        Provide[ApplicationContainer.media.get_file_tracks],
    ),
) -> dict[str, Any]:
    """Get available audio and subtitle tracks for a movie."""
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    file_path = _require_file(movie.file_path)
    tracks = await tracks_uc.execute(GetFileTracksInput(file_path=file_path))
    return asdict(tracks)


@router.get("/episode/{series_id}/{season_number}/{episode_number}/tracks")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_tracks(
    series_id: str,
    season_number: int,
    episode_number: int,
    profile_id: str = Depends(resolve_profile_id),
    series_uc: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
    tracks_uc: GetFileTracksUseCase = Depends(
        Provide[ApplicationContainer.media.get_file_tracks],
    ),
) -> dict[str, Any]:
    """Get available audio and subtitle tracks for an episode."""
    file_path = await _find_episode_file(
        series_uc, profile_id, series_id, season_number, episode_number
    )
    file_path = _require_file(file_path)
    tracks = await tracks_uc.execute(GetFileTracksInput(file_path=file_path))
    return asdict(tracks)


# -- Scrub-preview thumbnails (id-based) --------------------------------------
#
# Persisted by ``ThumbnailBackfillJob`` next to each media file
# (``<file_dir>/.homeflix/thumbnails/sprite.{vtt,jpg}``). The VTT
# references the JPG by relative filename — keep both URLs under the
# same path prefix so the player resolves the cue's ``sprite.jpg``
# reference against the VTT URL and lands on this route's ``.jpg``
# sibling.


def _scrub_preview_files(scrub_preview_path: str | None) -> tuple[Path, Path]:
    """Return (vtt_path, sprite_path) for a stored scrub-preview path, or 404.

    Validates both files in one place so the VTT route fails fast when
    the sprite is missing instead of returning cues whose ``sprite.jpg``
    references would 404 individually. ``None`` means the backfill job
    has not produced this preview yet; a missing file on disk means it
    ran at some point but was deleted out of band — both collapse to a
    404 the player handles by simply not showing previews.
    """
    if not scrub_preview_path:
        raise HTTPException(status_code=404, detail="Scrub preview not generated yet")
    vtt_path = Path(scrub_preview_path)
    sprite_path = vtt_path.with_name("sprite.jpg")
    if not vtt_path.is_file():
        raise HTTPException(status_code=404, detail="Scrub preview VTT missing on disk")
    if not sprite_path.is_file():
        raise HTTPException(status_code=404, detail="Scrub preview sprite missing on disk")
    return vtt_path, sprite_path


@router.get("/movie/{movie_id}/scrub-preview/sprite.vtt")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_scrub_preview_vtt(
    movie_id: str,
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> FileResponse:
    """Serve the persisted scrub-preview WebVTT for a movie."""
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    vtt_path, _ = _scrub_preview_files(movie.scrub_preview_path)
    return FileResponse(str(vtt_path), media_type="text/vtt")


@router.get("/movie/{movie_id}/scrub-preview/sprite.jpg")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def movie_scrub_preview_sprite(
    movie_id: str,
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
) -> FileResponse:
    """Serve the persisted scrub-preview sprite JPEG for a movie."""
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    _, sprite_path = _scrub_preview_files(movie.scrub_preview_path)
    return FileResponse(str(sprite_path), media_type="image/jpeg")


@router.get("/episode/{series_id}/{season_number}/{episode_number}/scrub-preview/sprite.vtt")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_scrub_preview_vtt(
    series_id: str,
    season_number: int,
    episode_number: int,
    profile_id: str = Depends(resolve_profile_id),
    series_uc: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> FileResponse:
    """Serve the persisted scrub-preview WebVTT for an episode."""
    episode = await _find_episode(series_uc, profile_id, series_id, season_number, episode_number)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    vtt_path, _ = _scrub_preview_files(episode.scrub_preview_path)
    return FileResponse(str(vtt_path), media_type="text/vtt")


@router.get("/episode/{series_id}/{season_number}/{episode_number}/scrub-preview/sprite.jpg")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def episode_scrub_preview_sprite(
    series_id: str,
    season_number: int,
    episode_number: int,
    profile_id: str = Depends(resolve_profile_id),
    series_uc: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
) -> FileResponse:
    """Serve the persisted scrub-preview sprite JPEG for an episode."""
    episode = await _find_episode(series_uc, profile_id, series_id, season_number, episode_number)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    _, sprite_path = _scrub_preview_files(episode.scrub_preview_path)
    return FileResponse(str(sprite_path), media_type="image/jpeg")


# -- Cache management ----------------------------------------------------------


@router.delete("/movie/{movie_id}/hls/cache")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def clear_movie_hls_cache(
    movie_id: str,
    _admin: UserModel = Depends(current_admin_user),
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    clear_uc: ClearHlsCacheUseCase = Depends(
        Provide[ApplicationContainer.media.clear_hls_cache],
    ),
) -> Response:
    """Clear cached HLS segments for a movie, forcing regeneration."""
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    await clear_uc.execute(ClearHlsCacheInput(file_path=movie.file_path))
    return Response(status_code=204)


# -- Direct streaming (fallback for MP4/WebM) ---------------------------------


@router.get("/movie/{movie_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def stream_movie(
    movie_id: str,
    request: Request,
    profile_id: str = Depends(resolve_profile_id),
    movie_uc: GetMovieByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_movie_by_id],
    ),
    stream_uc: StreamFileRangeUseCase = Depends(
        Provide[ApplicationContainer.media.stream_file_range],
    ),
) -> StreamingResponse:
    """Direct stream a movie file with Range support (MP4/WebM only)."""
    movie = await movie_uc.execute(GetMovieByIdInput(profile_id=profile_id, movie_id=movie_id))
    file_path = _require_file(movie.file_path)
    return await _stream_range(stream_uc, file_path, request.headers.get("range"))


@router.get("/episode/{series_id}/{season_number}/{episode_number}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def stream_episode(
    series_id: str,
    season_number: int,
    episode_number: int,
    request: Request,
    profile_id: str = Depends(resolve_profile_id),
    series_uc: GetSeriesByIdUseCase = Depends(
        Provide[ApplicationContainer.media.get_series_by_id],
    ),
    stream_uc: StreamFileRangeUseCase = Depends(
        Provide[ApplicationContainer.media.stream_file_range],
    ),
) -> StreamingResponse:
    """Direct stream an episode file with Range support."""
    file_path = await _find_episode_file(
        series_uc, profile_id, series_id, season_number, episode_number
    )
    file_path = _require_file(file_path)
    return await _stream_range(stream_uc, file_path, request.headers.get("range"))


# -- Helpers -------------------------------------------------------------------


async def _serve_master(
    use_case: GenerateHlsPlaylistUseCase,
    file_path: str,
    start: int = 0,
) -> Response:
    """Run the generate-playlist use case and wrap its DTO in a Response."""
    output = await use_case.execute(
        GenerateHlsPlaylistInput(
            file_path=file_path,
            base_url_template=_MASTER_BASE_URL,
            start=start,
        )
    )
    return Response(
        content=output.rewritten_content,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


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


async def _find_episode_file(
    use_case: GetSeriesByIdUseCase,
    profile_id: str,
    series_id: str,
    season_number: int,
    episode_number: int,
) -> str | None:
    """Find episode file path from series hierarchy."""
    episode = await _find_episode(use_case, profile_id, series_id, season_number, episode_number)
    return episode.file_path if episode else None


async def _find_episode(
    use_case: GetSeriesByIdUseCase,
    profile_id: str,
    series_id: str,
    season_number: int,
    episode_number: int,
) -> EpisodeOutput | None:
    """Resolve a single ``EpisodeOutput`` from the series aggregate."""
    series = await use_case.execute(GetSeriesByIdInput(profile_id=profile_id, series_id=series_id))
    for season in series.seasons:
        if season.season_number == season_number:
            for episode in season.episodes:
                if episode.episode_number == episode_number:
                    return episode
            break
    return None


__all__ = ["router"]
