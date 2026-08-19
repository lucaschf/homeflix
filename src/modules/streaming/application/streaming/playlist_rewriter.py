"""Pure m3u8 text utilities.

No ffmpeg, no filesystem access — just regex-based rewriting of
relative references and a suffix → MIME map. Lives in the application
layer so use cases and tests can exercise it without pulling in the
infrastructure ``HlsService``.
"""

import re
from pathlib import Path

# Matches standalone relative references (non-comment lines).
_RELATIVE_REF_RE = re.compile(
    r"^(?!#)(?!https?://)(?!/)(.+)$",
    re.MULTILINE,
)

# Matches ``URI="..."`` attributes with relative paths only
# (skips absolute/protocol URIs).
_URI_ATTR_RE = re.compile(r'URI="(?!https?://)(?!/)([^"]+)"')

# Identifies cache-relative paths under a ``sub_<index>/`` directory so
# route handlers / use cases can wait on the right per-subtitle
# extraction event.
SUB_PATH_RE = re.compile(r"^sub_(\d+)/")

_MEDIA_TYPES: dict[str, str] = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".vtt": "text/vtt",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def rewrite_m3u8(m3u8_text: str, base_url: str) -> str:
    """Prefix every relative reference in an m3u8 with ``base_url``."""
    result = _URI_ATTR_RE.sub(rf'URI="{base_url}/\1"', m3u8_text)
    return _RELATIVE_REF_RE.sub(rf"{base_url}/\1", result)


def media_type_for(filename: str) -> str:
    """Map a filename suffix to the matching HLS-adjacent MIME type."""
    suffix = Path(filename).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


__all__ = ["SUB_PATH_RE", "media_type_for", "rewrite_m3u8"]
