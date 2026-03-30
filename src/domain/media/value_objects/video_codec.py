"""Video codec enumeration."""

from enum import StrEnum


class VideoCodec(StrEnum):
    """Supported video codecs.

    Example:
        >>> codec = VideoCodec.H265
        >>> codec.value
        'h265'
    """

    H264 = "h264"
    H265 = "h265"
    AV1 = "av1"
    VP9 = "vp9"
    MPEG4 = "mpeg4"


__all__ = ["VideoCodec"]
