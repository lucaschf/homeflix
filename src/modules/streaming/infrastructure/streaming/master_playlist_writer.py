"""Master (multivariant) HLS playlist generation.

Extracted from ``HlsService`` (pure: builds one ``master.m3u8`` on disk
from a probe result). Emits ``#EXT-X-MEDIA`` renditions for alternate
audio and text subtitle tracks, with fallback display names composed from
the language code plus a structured version token (dub studio, channel
layout, ordinal, SDH).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.streaming.infrastructure.streaming._hls_common import primary_audio_index
from src.shared_kernel.track_selection.track_naming import (
    audio_version_labels,
    render_version_token,
    subtitle_version_labels,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.shared_kernel.media_probe.media_probe_port import ProbeResult
    from src.shared_kernel.track_selection.track_naming import TrackVersion

_logger = logging.getLogger(__name__)


def _manifest_track_name(language: str, version: TrackVersion | None) -> str:
    """Compose a fallback ``NAME=`` for a manifest rendition.

    The manifest can't carry structured data and isn't localized, so we
    use the language code plus a short version token (e.g. "PT",
    "PT · Herbert Richers", "PT · 5.1"). Clients should prefer the
    structured ``/tracks`` payload and localize it themselves.
    """
    base = language.upper()
    token = render_version_token(version)
    return f"{base} · {token}" if token else base


class MasterPlaylistWriter:
    """Write ``master.m3u8`` with audio renditions and subtitle tracks."""

    @staticmethod
    def write(output_dir: Path, probe: ProbeResult) -> None:
        """Generate master.m3u8 with audio renditions and subtitle tracks."""
        lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

        has_alt_audio = len(probe.audio_tracks) > 1
        audio_group = 'AUDIO="audio"' if has_alt_audio else ""
        text_subs = [s for s in probe.all_subtitles if s.is_text_based]
        sub_group = 'SUBTITLES="subs"' if text_subs else ""

        audio_versions = audio_version_labels(probe.audio_tracks)
        sub_versions = subtitle_version_labels(text_subs)

        primary_idx = primary_audio_index(probe)
        if has_alt_audio:
            for track in probe.audio_tracks:
                is_primary = track.index == primary_idx
                name = _manifest_track_name(track.language.value, audio_versions.get(track.index))
                if is_primary:
                    lines.append(
                        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                        f'NAME="{name}",LANGUAGE="{track.language.value}",'
                        f"DEFAULT=YES,AUTOSELECT=YES"
                    )
                else:
                    lines.append(
                        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                        f'NAME="{name}",LANGUAGE="{track.language.value}",'
                        f"DEFAULT=NO,AUTOSELECT=NO,"
                        f'URI="audio_{track.index}/playlist.m3u8"'
                    )

        for sub in text_subs:
            sub_name = _manifest_track_name(sub.language.value, sub_versions.get(sub.index))
            is_forced = "YES" if sub.is_forced else "NO"
            lines.append(
                f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",'
                f'NAME="{sub_name}",LANGUAGE="{sub.language.value}",'
                f"DEFAULT=NO,AUTOSELECT=NO,FORCED={is_forced},"
                f'URI="sub_{sub.index}/playlist.m3u8"'
            )

        groups = ",".join(filter(None, [audio_group, sub_group]))
        stream_inf = "#EXT-X-STREAM-INF:BANDWIDTH=5000000"
        if groups:
            stream_inf += f",{groups}"
        lines.append(stream_inf)
        lines.append("video/playlist.m3u8")

        master_path = output_dir / "master.m3u8"
        master_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _logger.info("Master playlist written to %s", master_path)


__all__ = ["MasterPlaylistWriter"]
