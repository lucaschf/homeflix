"""MediaFile value object for file variants."""

from datetime import datetime

from pydantic import Field

from src.building_blocks.domain import CompoundValueObject, utc_now
from src.modules.media.domain.value_objects.hdr_format import HdrFormat
from src.modules.media.domain.value_objects.resolution import Resolution
from src.modules.media.domain.value_objects.video_codec import VideoCodec
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


class MediaFile(CompoundValueObject):
    """A single file variant of a media item.

    Represents one physical file (e.g., a 1080p or 4K version) with its
    technical metadata, audio tracks, and subtitle tracks.

    Attributes:
        file_path: Absolute path to the video file.
        file_size: File size in bytes.
        resolution: Video resolution.
        video_codec: Video codec (h264, h265, etc.).
        video_bitrate: Video bitrate in kbps.
        hdr_format: HDR format if applicable.
        audio_tracks: Audio tracks in this file.
        subtitle_tracks: Subtitle tracks in this file.
        is_primary: Whether this is the primary (preferred) file variant.
        added_at: When this file variant was registered.

    Example:
        >>> media_file = MediaFile(
        ...     file_path=FilePath("/movies/inception_1080p.mkv"),
        ...     file_size=4_000_000_000,
        ...     resolution=Resolution("1080p"),
        ...     video_codec=VideoCodec.H265,
        ...     is_primary=True,
        ... )
    """

    file_path: FilePath
    file_size: int = Field(ge=0)
    resolution: Resolution
    video_codec: VideoCodec | None = None
    video_bitrate: int | None = Field(default=None, ge=0)
    hdr_format: HdrFormat | None = None
    audio_tracks: list[AudioTrack] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = Field(default_factory=list)
    is_primary: bool = False
    added_at: datetime = Field(default_factory=utc_now)


__all__ = ["MediaFile"]
