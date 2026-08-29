"""Tests for ServeHlsFileUseCase."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.streaming.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.streaming.application.use_cases.serve_hls_file import (
    ServeHlsFileInput,
    ServeHlsFileUseCase,
)

_BASE_URL = "/api/v1/stream/hls/{path_hash}{parent}"


def _make_hls_mock() -> MagicMock:
    return MagicMock(spec=HlsPlaylistPort)


@pytest.mark.unit
class TestServeHlsFileUseCase:
    @pytest.mark.asyncio
    async def test_should_return_file_output_for_non_playlist(self, tmp_path: Path) -> None:
        segment = tmp_path / "segment_0001.ts"
        segment.write_bytes(b"segment-bytes")

        hls = _make_hls_mock()
        hls.get_file_by_hash.return_value = segment
        use_case = ServeHlsFileUseCase(hls=hls)

        output = await use_case.execute(
            ServeHlsFileInput(
                path_hash="abc",
                relative_path="video/segment_0001.ts",
                base_url_template=_BASE_URL,
            )
        )

        assert output.kind == "file"
        assert output.path == segment
        assert output.media_type == "video/mp2t"

    @pytest.mark.asyncio
    async def test_should_rewrite_playlist_content(self, tmp_path: Path) -> None:
        sub_dir = tmp_path / "video"
        sub_dir.mkdir()
        playlist = sub_dir / "playlist.m3u8"
        playlist.write_text("#EXTM3U\nsegment_0001.ts\n", encoding="utf-8")

        hls = _make_hls_mock()
        hls.get_file_by_hash.return_value = playlist
        use_case = ServeHlsFileUseCase(hls=hls)

        output = await use_case.execute(
            ServeHlsFileInput(
                path_hash="abc",
                relative_path="video/playlist.m3u8",
                base_url_template=_BASE_URL,
            )
        )

        assert output.kind == "playlist"
        assert output.content is not None
        assert "/api/v1/stream/hls/abc/video/segment_0001.ts" in output.content

    @pytest.mark.asyncio
    async def test_should_wait_for_subtitle_before_resolving(self, tmp_path: Path) -> None:
        vtt = tmp_path / "sub.vtt"
        vtt.write_text("WEBVTT\n", encoding="utf-8")

        hls = _make_hls_mock()
        hls.get_file_by_hash.return_value = vtt
        hls.wait_for_subtitle.return_value = True
        use_case = ServeHlsFileUseCase(hls=hls)

        await use_case.execute(
            ServeHlsFileInput(
                path_hash="abc",
                relative_path="sub_2/sub.vtt",
                base_url_template=_BASE_URL,
            )
        )

        hls.wait_for_subtitle.assert_called_once()
        args = hls.wait_for_subtitle.call_args.args
        assert args[0] == "abc"
        assert args[1] == 2

    @pytest.mark.asyncio
    async def test_should_skip_subtitle_wait_for_other_paths(self, tmp_path: Path) -> None:
        segment = tmp_path / "segment.ts"
        segment.write_bytes(b"x")

        hls = _make_hls_mock()
        hls.get_file_by_hash.return_value = segment
        use_case = ServeHlsFileUseCase(hls=hls)

        await use_case.execute(
            ServeHlsFileInput(
                path_hash="abc",
                relative_path="video/segment.ts",
                base_url_template=_BASE_URL,
            )
        )

        hls.wait_for_subtitle.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_when_file_missing(self) -> None:
        hls = _make_hls_mock()
        hls.get_file_by_hash.return_value = None
        use_case = ServeHlsFileUseCase(hls=hls)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                ServeHlsFileInput(
                    path_hash="abc",
                    relative_path="missing.ts",
                    base_url_template=_BASE_URL,
                )
            )
