"""Persistence of probe results (``tracks.json``) in the HLS cache.

Extracted from ``HlsService`` (pure: filesystem reads/writes only, no
locks or threads). Serialises a :class:`ProbeResult` for the tracks API
and reconstructs it on cache hits, and reads the raw cached payload for
a bucket.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.media.application.ports.media_probe_port import ProbeResult


class ProbeCacheStore:
    """Read and write ``tracks.json`` probe caches under a cache root.

    Args:
        cache_dir: Root cache directory; each bucket lives at
            ``<cache_dir>/<path_hash>/``.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def get_cached_tracks(self, path_hash: str) -> dict[str, Any] | None:
        """Get cached probe result from tracks.json."""
        tracks_file = self._cache_dir / path_hash / "tracks.json"
        if not tracks_file.is_file():
            return None
        try:
            data: dict[str, Any] = json.loads(tracks_file.read_text(encoding="utf-8"))
            return data
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def save(output_dir: Path, probe: ProbeResult) -> None:
        """Save probe result as JSON for the tracks API."""
        data = {
            "resolution": probe.resolution,
            "audio_tracks": [
                {
                    "index": t.index,
                    "language": t.language.value,
                    "codec": t.codec,
                    "channels": t.channels,
                    "title": t.title,
                    "is_default": t.is_default,
                    "bitrate": t.bitrate,
                    "sample_rate": t.sample_rate,
                    "profile": t.profile,
                }
                for t in probe.audio_tracks
            ],
            "subtitle_tracks": [
                {
                    "index": t.index,
                    "language": t.language.value,
                    "format": t.format,
                    "title": t.title,
                    "is_default": t.is_default,
                    "is_forced": t.is_forced,
                    "is_external": t.is_external,
                    "is_image_based": t.is_image_based,
                }
                for t in probe.all_subtitles
            ],
        }
        (output_dir / "tracks.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def deserialize(data: dict[str, Any]) -> ProbeResult:
        """Reconstruct ProbeResult from cached JSON."""
        from src.modules.media.application.ports.media_probe_port import ProbeResult
        from src.shared_kernel.value_objects.language_code import LanguageCode
        from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

        audio = [
            AudioTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                codec=t["codec"],
                channels=t["channels"],
                title=t.get("title"),
                is_default=t["is_default"],
                bitrate=t.get("bitrate"),
                sample_rate=t.get("sample_rate"),
                profile=t.get("profile"),
            )
            for t in data.get("audio_tracks", [])
        ]
        subs = [
            SubtitleTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                format=t["format"],
                title=t.get("title"),
                is_default=t.get("is_default", False),
                is_forced=t.get("is_forced", False),
                is_external=t.get("is_external", False),
            )
            for t in data.get("subtitle_tracks", [])
            if not t.get("is_external", False)
        ]
        ext = [
            SubtitleTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                format=t["format"],
                title=t.get("title"),
                is_default=t.get("is_default", False),
                is_forced=t.get("is_forced", False),
                is_external=True,
                file_path=None,
            )
            for t in data.get("subtitle_tracks", [])
            if t.get("is_external", False)
        ]
        return ProbeResult(
            audio_tracks=audio,
            subtitle_tracks=subs,
            external_subtitles=ext,
            resolution=data.get("resolution"),
        )


__all__ = ["ProbeCacheStore"]
