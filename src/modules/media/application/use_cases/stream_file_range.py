"""StreamFileRangeUseCase — byte-range streaming for direct playback."""

from dataclasses import dataclass

from src.modules.media.application.dtos.stream_dtos import RangeStreamOutput
from src.modules.media.application.ports.file_streamer_port import FileStreamerPort
from src.modules.media.application.streaming.range_parser import parse_range_header

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

        if byte_range.is_partial:
            headers = {
                "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(byte_range.length),
            }
            return RangeStreamOutput(
                status_code=206,
                media_type=input_dto.media_type,
                headers=headers,
                body=body,
            )

        return RangeStreamOutput(
            status_code=200,
            media_type=input_dto.media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
            body=body,
        )


__all__ = ["StreamFileRangeInput", "StreamFileRangeUseCase"]
