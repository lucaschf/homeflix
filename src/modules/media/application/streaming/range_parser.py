"""HTTP ``Range`` header parsing.

Pure helper so the use case for byte-range streaming can test the
parsing logic without spinning up FastAPI. We handle only the single
``bytes=<start>-<end>`` form the frontend's native video element
sends — multipart range requests are out of scope.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ByteRange:
    """An inclusive byte range clamped to a given file size.

    Attributes:
        start: First byte to send (``0`` when no range).
        end: Last byte to send, inclusive.
        is_partial: ``True`` when the source was a real ``Range`` header,
            ``False`` when the caller sent no ``Range`` (full file).
    """

    start: int
    end: int
    is_partial: bool

    @property
    def length(self) -> int:
        """Number of bytes covered by the range, inclusive."""
        return self.end - self.start + 1


def parse_range_header(range_header: str | None, file_size: int) -> ByteRange:
    """Return the inclusive ``ByteRange`` described by a ``Range`` header.

    Args:
        range_header: Raw ``Range`` header value (e.g. ``"bytes=0-1024"``)
            or ``None`` when the client omitted it.
        file_size: Length of the underlying file in bytes.

    Returns:
        ``ByteRange`` covering the full file when ``range_header`` is
        ``None``, otherwise the clamped requested range.
    """
    if not range_header:
        return ByteRange(start=0, end=max(0, file_size - 1), is_partial=False)

    spec = range_header.replace("bytes=", "")
    parts = spec.split("-")
    start = int(parts[0]) if parts[0] else 0
    end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
    start = max(0, start)
    end = min(end, file_size - 1)
    return ByteRange(start=start, end=end, is_partial=True)


__all__ = ["ByteRange", "parse_range_header"]
