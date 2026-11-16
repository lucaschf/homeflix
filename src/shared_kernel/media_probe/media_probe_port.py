"""Port for probing audio/subtitle/resolution metadata from media files.

The scan and streaming use cases need to inspect a media file's
tracks without depending on the concrete ffprobe-backed service.
This port owns the ``ProbeResult`` DTO; infrastructure returns it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


@dataclass(frozen=True)
class ProbeResult:
    """Snapshot of tracks + resolution extracted from a media file.

    Attributes:
        audio_tracks: Embedded audio streams.
        subtitle_tracks: Embedded subtitle streams.
        external_subtitles: Sidecar ``.srt`` / ``.ass`` / ``.vtt`` files
            discovered next to the probed video.
        resolution: Named resolution (``"1080p"``, ``"4K"``, …) or
            ``None`` when the video stream is missing or below 360p.
        duration_seconds: Duration the container declares, in whole seconds,
            or ``None`` when ffprobe could not read it. A subtitle or a dub
            can stretch it past the picture, so use
            :meth:`MediaProbePort.probe_duration` for how long a title runs.
    """

    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    external_subtitles: list[SubtitleTrack] = field(default_factory=list)
    resolution: str | None = None
    duration_seconds: int | None = None

    @property
    def all_subtitles(self) -> list[SubtitleTrack]:
        """All subtitle tracks (embedded + external)."""
        return [*self.subtitle_tracks, *self.external_subtitles]

    @property
    def text_subtitles(self) -> list[SubtitleTrack]:
        """Only text-based subtitles convertible to WebVTT."""
        return [s for s in self.all_subtitles if s.is_text_based]


class MediaProbePort(ABC):
    """Inspect a media file for audio/subtitle/resolution metadata."""

    @abstractmethod
    def probe(self, file_path: str) -> ProbeResult:
        """Return the full probe result for the given file.

        Implementations must return a ``ProbeResult`` even on failure
        (empty tracks, ``resolution=None``); the use case branches on
        the contents, never on exceptions.
        """
        ...

    def probe_resolution(self, file_path: str) -> str | None:
        """Return only the named resolution (convenience over ``probe``).

        Default implementation delegates to ``probe``; override only
        when the adapter can produce the resolution more cheaply than
        a full probe.
        """
        return self.probe(file_path).resolution

    def probe_duration(self, file_path: str) -> int | None:
        """Return how long the title runs in whole seconds, or ``None``.

        This is the real file duration (the source of truth for playback),
        distinct from a metadata provider's nominal runtime. Default
        implementation delegates to ``probe``; override when the adapter can
        measure the media itself. It may read more of the file than ``probe``,
        so it is meant for registering a file, not for starting playback.
        """
        return self.probe(file_path).duration_seconds


__all__ = ["MediaProbePort", "ProbeResult"]
