"""Unit tests for the HLS streaming route handlers.

The routes are deliberately thin: resolve the movie/episode through the
``MediaPlaybackLookupPort``, validate the file, hand the path to a
streaming use case, and map the returned DTO onto a FastAPI response.
These tests call the handler coroutines directly with mocked ports/use
cases so the presentation branches — status mapping, response wiring, the
eager-backfill trigger, and the episode segment-translation math — are
covered without FFmpeg, disk, auth, or a live ASGI stack.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.streaming.application.dtos.stream_dtos import (
    HlsFileOutput,
    TrackListOutput,
)
from src.modules.streaming.application.ports.media_lookup_port import (
    EpisodePlaybackInfo,
    MoviePlaybackInfo,
)
from src.modules.streaming.presentation.routes import hls_routes as mod

pytestmark = pytest.mark.unit


def _request(range_header: str | None = None, user_agent: str | None = "pytest-UA") -> object:
    """Minimal stand-in for a Starlette ``Request``.

    Only ``.client.host`` and ``.headers.get`` are touched by the handlers.
    """
    headers = {}
    if range_header is not None:
        headers["range"] = range_header
    if user_agent is not None:
        headers["user-agent"] = user_agent
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers=headers)


async def _drain_eager() -> None:
    """Await any fire-and-forget scrub-preview backfill tasks."""
    while mod._eager_thumbnail_tasks:
        await asyncio.gather(*list(mod._eager_thumbnail_tasks), return_exceptions=True)


def _movie(
    *,
    file_path: str | None,
    scrub_preview_path: str | None = "/prev/sprite.vtt",
) -> MoviePlaybackInfo:
    return MoviePlaybackInfo(
        file_path=file_path,
        scrub_preview_path=scrub_preview_path,
        title="The Movie",
        year=2024,
        resolution="1080p",
        poster_path="/posters/m.jpg",
        duration_seconds=7200,
    )


def _episode(
    *,
    file_path: str | None,
    scrub_preview_path: str | None = "/prev/e.vtt",
    segment_start_seconds: int | None = None,
    segment_end_seconds: int | None = None,
) -> EpisodePlaybackInfo:
    return EpisodePlaybackInfo(
        episode_id="epi_aaaaaaaaaaaa",
        file_path=file_path,
        scrub_preview_path=scrub_preview_path,
        title="Pilot",
        duration_seconds=1400,
        segment_start_seconds=segment_start_seconds,
        segment_end_seconds=segment_end_seconds,
        series_title="The Series",
    )


def _lookup_movie(movie: MoviePlaybackInfo) -> MagicMock:
    lookup = MagicMock()
    lookup.find_movie = AsyncMock(return_value=movie)
    return lookup


def _lookup_episode(episode: EpisodePlaybackInfo | None) -> MagicMock:
    lookup = MagicMock()
    lookup.find_episode = AsyncMock(return_value=episode)
    return lookup


class TestHlsFile:
    async def test_returns_no_cache_response_for_playlist_output(self) -> None:
        use_case = AsyncMock()
        use_case.execute.return_value = HlsFileOutput(
            kind="playlist",
            media_type="application/vnd.apple.mpegurl",
            content="#EXTM3U",
        )

        result = await mod.hls_file("hash123", "index.m3u8", use_case=use_case)

        assert isinstance(result, Response)
        assert result.body == b"#EXTM3U"
        assert result.headers["Cache-Control"] == "no-cache"

    async def test_returns_file_response_for_segment_output(self, tmp_path: Path) -> None:
        seg = tmp_path / "seg0.ts"
        seg.write_bytes(b"\x00\x01")
        use_case = AsyncMock()
        use_case.execute.return_value = HlsFileOutput(
            kind="file",
            media_type="video/mp2t",
            path=seg,
        )

        result = await mod.hls_file("hash123", "seg0.ts", use_case=use_case)

        assert isinstance(result, FileResponse)
        assert result.media_type == "video/mp2t"

    async def test_maps_not_found_to_404(self) -> None:
        use_case = AsyncMock()
        use_case.execute.side_effect = ResourceNotFoundException.for_resource("HlsFile", "x")

        with pytest.raises(HTTPException) as exc_info:
            await mod.hls_file("hash123", "missing.ts", use_case=use_case)

        assert exc_info.value.status_code == 404

    async def test_raises_when_file_output_has_no_path(self) -> None:
        use_case = AsyncMock()
        use_case.execute.return_value = HlsFileOutput(kind="file", media_type="video/mp2t")

        with pytest.raises(RuntimeError):
            await mod.hls_file("hash123", "seg0.ts", use_case=use_case)


class TestMovieHlsPlaylist:
    async def test_serves_master_and_fires_backfill_when_no_preview(self, tmp_path: Path) -> None:
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"\x00")
        lookup = _lookup_movie(_movie(file_path=str(video), scrub_preview_path=None))
        hls_uc = AsyncMock()
        hls_uc.execute.return_value = SimpleNamespace(rewritten_content="#EXTM3U:master")
        backfill = SimpleNamespace(process_movie_by_id=AsyncMock(return_value=True))

        try:
            result = await mod.movie_hls_playlist(
                "mov_aaaaaaaaaaaa",
                _request(),
                start=0,
                profile_id="prf_aaaaaaaaaaaa",
                media_lookup=lookup,
                hls_uc=hls_uc,
                backfill_job=backfill,
            )
            await _drain_eager()
        finally:
            await _drain_eager()

        assert isinstance(result, Response)
        assert result.body == b"#EXTM3U:master"
        backfill.process_movie_by_id.assert_awaited_once_with("mov_aaaaaaaaaaaa")

    async def test_does_not_fire_backfill_when_preview_exists(self, tmp_path: Path) -> None:
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"\x00")
        lookup = _lookup_movie(_movie(file_path=str(video)))  # preview present
        hls_uc = AsyncMock()
        hls_uc.execute.return_value = SimpleNamespace(rewritten_content="#EXTM3U")
        backfill = SimpleNamespace(process_movie_by_id=AsyncMock(return_value=True))

        await mod.movie_hls_playlist(
            "mov_aaaaaaaaaaaa",
            _request(),
            start=0,
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            hls_uc=hls_uc,
            backfill_job=backfill,
        )
        await _drain_eager()

        backfill.process_movie_by_id.assert_not_awaited()

    async def test_404_when_movie_file_missing_on_disk(self) -> None:
        lookup = _lookup_movie(_movie(file_path="/nope/ghost.mkv"))
        with pytest.raises(HTTPException) as exc_info:
            await mod.movie_hls_playlist(
                "mov_aaaaaaaaaaaa",
                _request(),
                start=0,
                profile_id="prf_aaaaaaaaaaaa",
                media_lookup=lookup,
                hls_uc=AsyncMock(),
                backfill_job=SimpleNamespace(process_movie_by_id=AsyncMock()),
            )
        assert exc_info.value.status_code == 404


class TestEpisodeHlsPlaylist:
    async def test_404_when_episode_absent_from_series(self) -> None:
        lookup = _lookup_episode(None)  # series present, no such episode
        with pytest.raises(HTTPException) as exc_info:
            await mod.episode_hls_playlist(
                "ser_aaaaaaaaaaaa",
                1,
                99,
                _request(),
                start=0,
                profile_id="prf_aaaaaaaaaaaa",
                media_lookup=lookup,
                hls_uc=AsyncMock(),
                backfill_job=SimpleNamespace(process_episode_by_id=AsyncMock()),
            )
        assert exc_info.value.status_code == 404

    async def test_translates_start_into_file_coordinates_for_shared_file(
        self, tmp_path: Path
    ) -> None:
        # ADR-030: an episode that is a sub-range [600, 1800) of a shared
        # file. A player-relative start of 120 must map to file-absolute
        # 720, and the encode must stop at the segment end (1800).
        video = tmp_path / "shared.mkv"
        video.write_bytes(b"\x00")
        ep = _episode(
            file_path=str(video),
            segment_start_seconds=600,
            segment_end_seconds=1800,
        )
        lookup = _lookup_episode(ep)
        hls_uc = AsyncMock()
        hls_uc.execute.return_value = SimpleNamespace(rewritten_content="#EXTM3U")

        await mod.episode_hls_playlist(
            "ser_aaaaaaaaaaaa",
            1,
            1,
            _request(),
            start=120,
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            hls_uc=hls_uc,
            backfill_job=SimpleNamespace(process_episode_by_id=AsyncMock()),
        )
        await _drain_eager()

        sent = hls_uc.execute.await_args.args[0]
        assert sent.start == 720
        assert sent.end == 1800


class TestMovieTracks:
    async def test_serializes_track_list_output(self, tmp_path: Path) -> None:
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"\x00")
        lookup = _lookup_movie(_movie(file_path=str(video)))
        tracks_uc = AsyncMock()
        tracks_uc.execute.return_value = TrackListOutput(
            audio_tracks=[{"index": 0, "language": "eng"}],
            subtitle_tracks=[],
        )

        result = await mod.movie_tracks(
            "mov_aaaaaaaaaaaa",
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            tracks_uc=tracks_uc,
        )

        assert result == {
            "audio_tracks": [{"index": 0, "language": "eng"}],
            "subtitle_tracks": [],
        }


class TestClearMovieHlsCache:
    async def test_returns_204(self) -> None:
        lookup = _lookup_movie(_movie(file_path="/movies/m.mkv"))
        clear_uc = AsyncMock()

        result = await mod.clear_movie_hls_cache(
            "mov_aaaaaaaaaaaa",
            _admin=SimpleNamespace(),
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            clear_uc=clear_uc,
        )

        assert result.status_code == 204
        clear_uc.execute.assert_awaited_once()
