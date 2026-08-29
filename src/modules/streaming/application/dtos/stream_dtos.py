"""DTOs for the stream use cases.

Each output encapsulates everything the route needs to build an HTTP
response so presentation code stays free of streaming concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.shared_kernel.track_selection.track_naming import (
    TrackVersion,
    audio_version_labels,
    subtitle_version_labels,
)
from src.shared_kernel.track_selection.track_selector import TrackSelector

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.streaming.application.ports.profile_playback_preference_port import (
        PlaybackPreference,
    )
    from src.shared_kernel.media_probe.media_probe_port import ProbeResult


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


def _version_dict(version: TrackVersion | None) -> dict[str, str] | None:
    """Project a structured ``TrackVersion`` into a JSON-friendly dict."""
    if version is None:
        return None
    return {"kind": version.kind, "value": version.value}


def serialize_tracks(
    probe: ProbeResult,
    preference: PlaybackPreference | None = None,
) -> TrackListOutput:
    """Project a ``ProbeResult`` into the flat track DTO.

    Each track carries a structured ``version`` differentiating it from
    same-language siblings (e.g. a dub studio, channel layout, or an
    ordinal), or ``None`` when the language alone is unambiguous. The
    raw ``title`` is kept for reference; the player should prefer the
    language + ``version`` and localize them.

    Args:
        probe: The probed track list for the file.
        preference: The viewer profile's playback preference (ADR-026,
            resolved server-side from the Preferences BC), or ``None`` when
            unavailable. When present, the audio and subtitle defaults are
            server-resolved via :class:`TrackSelector`; when ``None`` the
            audio default falls back to the container default (else first)
            and each subtitle keeps its container-declared ``is_default``.
    """
    audio_versions = audio_version_labels(probe.audio_tracks)
    text_subs = [t for t in probe.all_subtitles if t.is_text_based]
    sub_versions = subtitle_version_labels(text_subs)
    # The probe reports ``is_default`` truthfully (container-declared only);
    # the ADR-005/026 selector resolves the player's defaults from the
    # profile preference (exactly one default audio, and at most one subtitle).
    selector = TrackSelector()
    default_audio = selector.select_audio(
        probe.audio_tracks, preference.audio_language if preference else None
    )
    # ``preference is not None`` (not the ``resolve_subtitle`` flag) so mypy
    # narrows the Optional before we read ``preference.subtitle_*`` below.
    resolve_subtitle = preference is not None
    default_subtitle = None
    if preference is not None:
        chosen_audio_language = default_audio.language if default_audio else None
        default_subtitle = selector.select_subtitle(
            text_subs,
            chosen_audio_language,
            preference.subtitle_language,
            preference.subtitle_mode,
        )
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
                "is_default": t is default_audio,
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
                "is_default": (t is default_subtitle) if resolve_subtitle else t.is_default,
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
    "TrackListOutput",
    "serialize_tracks",
]
