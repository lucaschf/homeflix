"""Neutral shared helpers and constants for the HLS streaming package.

Housed here — rather than on ``hls_service`` — so the extracted seams
(the transcode command builder and the master-playlist writer) can depend
on them without importing ``hls_service`` back. ``hls_service`` imports the
seams, so a seam importing ``hls_service`` would be a circular import; this
module has no such dependency and stays safe to import from either side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.shared_kernel.media_probe.media_probe_port import ProbeResult

# seconds per segment
SEGMENT_DURATION = 10

# Video codecs a browser can play as-is, so the pipeline can remux instead
# of transcoding. Shared by the command builder (video cmd) and the
# orchestrator (HW-transcode eligibility decision).
BROWSER_SAFE_CODECS = {"h264"}

_VIDEO_DIR = "video"

# Prefix marking a bucket dir that has been renamed out of the live cache
# path and is awaiting deletion. The eviction scan skips (and retries
# cleaning) these so they are never mistaken for a real bucket.
_EVICTING_PREFIX = ".evicting-"


def primary_audio_index(probe: ProbeResult) -> int:
    """Get the index of the primary audio track (first one, always index 0)."""
    return probe.audio_tracks[0].index if probe.audio_tracks else 0


def _has_endlist(playlist_path: Path) -> bool:
    """Return ``True`` iff the playlist file exists and contains ``#EXT-X-ENDLIST``."""
    try:
        return "#EXT-X-ENDLIST" in playlist_path.read_text(encoding="utf-8")
    except OSError:
        return False
