"""Unit tests for the direct byte-range streaming route handlers.

Call the handler coroutines directly with a mocked
``MediaPlaybackLookupPort`` and ``StreamFileRangeUseCase`` so the
presentation branches — file 404s, episode-not-found, and the
range-streaming response wrapping — are covered without an ASGI stack.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.modules.streaming.application.dtos.range_stream_dtos import RangeStreamOutput
from src.modules.streaming.application.ports.media_lookup_port import (
    EpisodePlaybackInfo,
    MoviePlaybackInfo,
)
from src.modules.streaming.presentation.routes import direct_stream_routes as mod

pytestmark = pytest.mark.unit


def _request(range_header: str | None = "bytes=0-") -> object:
    headers = {"range": range_header} if range_header is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers=headers)


def _movie(file_path: str | None) -> MoviePlaybackInfo:
    return MoviePlaybackInfo(
        file_path=file_path,
        scrub_preview_path=None,
        title="The Movie",
        year=2024,
        resolution="1080p",
        poster_path=None,
        duration_seconds=7200,
    )


def _episode(file_path: str | None) -> EpisodePlaybackInfo:
    return EpisodePlaybackInfo(
        episode_id="epi_aaaaaaaaaaaa",
        file_path=file_path,
        scrub_preview_path=None,
        title="Pilot",
        duration_seconds=1400,
        segment_start_seconds=None,
        segment_end_seconds=None,
        series_title="The Series",
    )


def _range_uc() -> AsyncMock:
    async def _body() -> object:
        yield b"chunk"

    uc = AsyncMock()
    uc.execute.return_value = RangeStreamOutput(
        status_code=206,
        media_type="video/mp4",
        headers={"Content-Range": "bytes 0-4/5"},
        body=_body(),
    )
    return uc


class TestStreamMovie:
    async def test_wraps_range_output_in_streaming_response(self, tmp_path: Path) -> None:
        video = tmp_path / "movie.mp4"
        video.write_bytes(b"\x00")
        lookup = AsyncMock()
        lookup.find_movie.return_value = _movie(str(video))

        result = await mod.stream_movie(
            "mov_aaaaaaaaaaaa",
            _request(),
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            stream_uc=_range_uc(),
        )

        assert isinstance(result, StreamingResponse)
        assert result.status_code == 206
        lookup.find_movie.assert_awaited_once_with("prf_aaaaaaaaaaaa", "mov_aaaaaaaaaaaa")

    async def test_404_when_movie_file_missing_on_disk(self) -> None:
        lookup = AsyncMock()
        lookup.find_movie.return_value = _movie("/nope/ghost.mkv")
        with pytest.raises(HTTPException) as exc_info:
            await mod.stream_movie(
                "mov_aaaaaaaaaaaa",
                _request(),
                profile_id="prf_aaaaaaaaaaaa",
                media_lookup=lookup,
                stream_uc=AsyncMock(),
            )
        assert exc_info.value.status_code == 404


class TestStreamEpisode:
    async def test_streams_when_episode_resolved(self, tmp_path: Path) -> None:
        video = tmp_path / "ep.mp4"
        video.write_bytes(b"\x00")
        lookup = AsyncMock()
        lookup.find_episode.return_value = _episode(str(video))

        result = await mod.stream_episode(
            "ser_aaaaaaaaaaaa",
            1,
            1,
            _request(),
            profile_id="prf_aaaaaaaaaaaa",
            media_lookup=lookup,
            stream_uc=_range_uc(),
        )

        assert isinstance(result, StreamingResponse)
        assert result.status_code == 206

    async def test_404_when_episode_absent(self) -> None:
        lookup = AsyncMock()
        lookup.find_episode.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await mod.stream_episode(
                "ser_aaaaaaaaaaaa",
                1,
                99,
                _request(),
                profile_id="prf_aaaaaaaaaaaa",
                media_lookup=lookup,
                stream_uc=AsyncMock(),
            )
        assert exc_info.value.status_code == 404
