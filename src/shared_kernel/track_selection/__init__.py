"""Shared track-selection domain logic.

Track selection (:class:`TrackSelector`) and track naming/versioning
helpers live in the shared kernel because both the Media catalog and the
Streaming context reason about the same audio/subtitle track VOs
(``AudioTrack`` / ``SubtitleTrack``) — Media when summarizing files,
Streaming when building the player's track list and master playlist.
"""

from src.shared_kernel.track_selection.track_naming import (
    TrackVersion,
    audio_version_labels,
    detect_studio,
    render_version_token,
    subtitle_version_labels,
)
from src.shared_kernel.track_selection.track_selector import TrackSelector

__all__ = [
    "TrackSelector",
    "TrackVersion",
    "audio_version_labels",
    "detect_studio",
    "render_version_token",
    "subtitle_version_labels",
]
