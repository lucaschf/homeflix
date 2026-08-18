"""StreamFileRangeUseCase — byte-range streaming for direct playback."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from src.modules.streaming.application.dtos.range_stream_dtos import RangeStreamOutput
from src.modules.streaming.application.helpers.range_parser import ByteRange, parse_range_header
from src.modules.streaming.application.ports.file_streamer_port import FileStreamerPort

_DEFAULT_MEDIA_TYPE = "video/mp4"


@dataclass(frozen=True)
class StreamFileRangeInput:
    """Inputs for byte-range streaming.

    Attributes:
        file_path: Absolute path to the file to stream.
        range_header: Raw HTTP ``Range`` header value (or ``None``).
        media_type: MIME type to return; defaults to ``video/mp4`` —
            routes can override for other containers if needed.
    """

    file_path: str
    range_header: str | None
    media_type: str = _DEFAULT_MEDIA_TYPE


class StreamFileRangeUseCase:
    """Build the byte-range response pieces for a local file."""

    def __init__(self, file_streamer: FileStreamerPort) -> None:
        self._streamer = file_streamer

    async def execute(self, input_dto: StreamFileRangeInput) -> RangeStreamOutput:
        """Resolve the requested byte range and return the streaming DTO."""
        file_size = self._streamer.get_file_size(input_dto.file_path)
        byte_range = parse_range_header(input_dto.range_header, file_size)
        body = self._streamer.stream_range(
            input_dto.file_path,
            byte_range.start,
            byte_range.end,
        )
        return self._build_output(input_dto.media_type, file_size, byte_range, body)

    @staticmethod
    def _build_output(
        media_type: str,
        file_size: int,
        byte_range: ByteRange,
        body: AsyncIterator[bytes],
    ) -> RangeStreamOutput:
        """Assemble status code + headers around ``body`` based on ``byte_range``."""
        headers = {"Accept-Ranges": "bytes"}
        if byte_range.is_partial:
            headers["Content-Range"] = f"bytes {byte_range.start}-{byte_range.end}/{file_size}"
            headers["Content-Length"] = str(byte_range.length)
            status_code = 206
        else:
            headers["Content-Length"] = str(file_size)
            status_code = 200

        return RangeStreamOutput(
            status_code=status_code,
            media_type=media_type,
            headers=headers,
            body=body,
        )


__all__ = ["StreamFileRangeInput", "StreamFileRangeUseCase"]
