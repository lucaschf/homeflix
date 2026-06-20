"""DTOs for the stream use cases.

Each output encapsulates everything the route needs to build an HTTP
response so presentation code stays free of streaming concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.modules.media.domain.services.track_naming import (
    TrackVersion,
    audio_version_labels,
    subtitle_version_labels,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from src.modules.media.application.ports.media_probe_port import ProbeResult


@dataclass(frozen=True)
class HlsPlaylistOutput:
    """Master playlist ready to be served.

    Attributes:
        path_hash: Cache key for subsequent segment/subtitle requests.
        rewritten_content: The ``master.m3u8`` with relative references
            already prefixed with the stream base URL.
    """

    path_hash: str
    rewritten_content: str


@dataclass(frozen=True)
class HlsFileOutput:
    """A cached HLS file resolved by path hash.

    ``kind`` discriminates how the route should build its response:

    - ``"playlist"``: ``content`` is the rewritten m3u8 text.
    - ``"file"``: ``path`` points to the on-disk file; ``media_type``
      carries the MIME the route should serve it as.
    """

    kind: Literal["playlist", "file"]
    media_type: str
    content: str | None = None
    path: Path | None = None


@dataclass(frozen=True)
class TrackListOutput:
    """Serialized audio + subtitle tracks for the player UI."""

    audio_tracks: list[dict[str, object]]
    subtitle_tracks: list[dict[str, object]]


@dataclass(frozen=True)
class RangeStreamOutput:
    """Byte-range streaming response pieces.

    ``body`` is the async generator of chunks to stream; the route
    wraps it in a FastAPI ``StreamingResponse`` with the provided
    status code and headers so response construction stays in
    presentation.
    """

    status_code: int
    media_type: str
    headers: dict[str, str]
    body: AsyncIterator[bytes]


def _version_dict(version: TrackVersion | None) -> dict[str, str] | None:
    """Project a structured ``TrackVersion`` into a JSON-friendly dict."""
    if version is None:
        return None
    return {"kind": version.kind, "value": version.value}


def serialize_tracks(probe: ProbeResult) -> TrackListOutput:
    """Project a ``ProbeResult`` into the flat track DTO.

    Each track carries a structured ``version`` differentiating it from
    same-language siblings (e.g. a dub studio, channel layout, or an
    ordinal), or ``None`` when the language alone is unambiguous. The
    raw ``title`` is kept for reference; the player should prefer the
    language + ``version`` and localize them.
    """
    audio_versions = audio_version_labels(probe.audio_tracks)
    text_subs = [t for t in probe.all_subtitles if t.is_text_based]
    sub_versions = subtitle_version_labels(text_subs)
    return TrackListOutput(
        audio_tracks=[
            {
                "index": t.index,
                "language": t.language.value,
                "codec": t.codec,
                "channels": t.channels,
                "channel_layout": t.channel_layout,
                "title": t.title,
                "version": _version_dict(audio_versions.get(t.index)),
                "is_default": t.is_default,
            }
            for t in probe.audio_tracks
        ],
        subtitle_tracks=[
            {
                "index": t.index,
                "language": t.language.value,
                "format": t.format,
                "title": t.title,
                "version": _version_dict(sub_versions.get(t.index)),
                "is_default": t.is_default,
                "is_forced": t.is_forced,
                "is_external": t.is_external,
                "is_image_based": t.is_image_based,
            }
            for t in text_subs
        ],
    )


__all__ = [
    "HlsFileOutput",
    "HlsPlaylistOutput",
    "RangeStreamOutput",
    "TrackListOutput",
    "serialize_tracks",
]
