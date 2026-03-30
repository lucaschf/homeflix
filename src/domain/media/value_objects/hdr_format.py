"""HDR format enumeration."""

from enum import StrEnum


class HdrFormat(StrEnum):
    """Supported HDR formats.

    Example:
        >>> fmt = HdrFormat.HDR10
        >>> fmt.value
        'hdr10'
    """

    HDR10 = "hdr10"
    HDR10_PLUS = "hdr10+"
    DOLBY_VISION = "dolby_vision"
    HLG = "hlg"


__all__ = ["HdrFormat"]
