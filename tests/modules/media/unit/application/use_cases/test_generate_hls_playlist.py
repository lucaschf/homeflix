"""Tests for GenerateHlsPlaylistUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.use_cases.generate_hls_playlist import (
    GenerateHlsPlaylistInput,
    GenerateHlsPlaylistUseCase,
)


def _make_hls_mock(
    path_hash: str = "abc123",
    master_content: str | None = "#EXTM3U\nvideo/playlist.m3u8\n",
) -> MagicMock:
    hls = MagicMock(spec=HlsPlaylistPort)
    hls.ensure_playlist = AsyncMock(return_value=path_hash)
    hls.get_master_playlist = MagicMock(return_value=master_content)
    return hls


@pytest.mark.unit
class TestGenerateHlsPlaylistUseCase:
    @pytest.mark.asyncio
    async def test_should_rewrite_relative_references(self) -> None:
        hls = _make_hls_mock(
            path_hash="abc",
            master_content="#EXTM3U\nvideo/playlist.m3u8\n",
        )
        use_case = GenerateHlsPlaylistUseCase(hls=hls)

        output = await use_case.execute(
            GenerateHlsPlaylistInput(
                file_path="/movies/file.mkv",
                base_url_template="/api/v1/stream/hls/{path_hash}",
            )
        )

        assert output.path_hash == "abc"
        assert "/api/v1/stream/hls/abc/video/playlist.m3u8" in output.rewritten_content
        hls.ensure_playlist.assert_awaited_once_with("/movies/file.mkv")

    @pytest.mark.asyncio
    async def test_should_raise_when_master_playlist_missing(self) -> None:
        hls = _make_hls_mock(master_content=None)
        use_case = GenerateHlsPlaylistUseCase(hls=hls)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GenerateHlsPlaylistInput(
                    file_path="/a.mkv",
                    base_url_template="/base/{path_hash}",
                )
            )
        assert exc_info.value.resource_type == "HlsMasterPlaylist"
