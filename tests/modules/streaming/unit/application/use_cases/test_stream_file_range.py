"""Tests for StreamFileRangeUseCase."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest

from src.modules.streaming.application.ports.file_streamer_port import FileStreamerPort
from src.modules.streaming.application.use_cases.stream_file_range import (
    StreamFileRangeInput,
    StreamFileRangeUseCase,
)


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


async def _fake_chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _make_streamer(file_size: int = 1000, body: bytes = b"x") -> MagicMock:
    streamer = MagicMock(spec=FileStreamerPort)
    streamer.get_file_size.return_value = file_size
    streamer.stream_range.return_value = _fake_chunks(body)
    return streamer


@pytest.mark.unit
class TestStreamFileRangeUseCase:
    @pytest.mark.asyncio
    async def test_should_return_full_file_with_200_when_no_range_header(self) -> None:
        streamer = _make_streamer(file_size=1000, body=b"full")
        use_case = StreamFileRangeUseCase(file_streamer=streamer)

        output = await use_case.execute(
            StreamFileRangeInput(file_path="/m.mp4", range_header=None),
        )

        assert output.status_code == 200
        assert output.headers["Content-Length"] == "1000"
        assert "Content-Range" not in output.headers
        streamer.stream_range.assert_called_once_with("/m.mp4", 0, 999)
        assert await _collect(output.body) == b"full"

    @pytest.mark.asyncio
    async def test_should_return_206_with_content_range_for_partial(self) -> None:
        streamer = _make_streamer(file_size=1000, body=b"partial")
        use_case = StreamFileRangeUseCase(file_streamer=streamer)

        output = await use_case.execute(
            StreamFileRangeInput(file_path="/m.mp4", range_header="bytes=100-199"),
        )

        assert output.status_code == 206
        assert output.headers["Content-Range"] == "bytes 100-199/1000"
        assert output.headers["Content-Length"] == "100"
        streamer.stream_range.assert_called_once_with("/m.mp4", 100, 199)

    @pytest.mark.asyncio
    async def test_should_clamp_range_end_to_file_size(self) -> None:
        streamer = _make_streamer(file_size=1000)
        use_case = StreamFileRangeUseCase(file_streamer=streamer)

        output = await use_case.execute(
            StreamFileRangeInput(file_path="/m.mp4", range_header="bytes=500-9999"),
        )

        assert output.status_code == 206
        assert output.headers["Content-Range"] == "bytes 500-999/1000"
