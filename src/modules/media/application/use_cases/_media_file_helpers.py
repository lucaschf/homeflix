"""Shared helpers for media file variant use cases."""

from src.modules.media.application.dtos.media_file_dtos import (
    AudioTrackOutput,
    MediaFileOutput,
    SubtitleTrackOutput,
)
from src.modules.media.domain.value_objects import MediaFile
from src.shared_kernel.track_selection.track_selector import TrackSelector
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _to_audio_track_output(track: AudioTrack, *, is_default: bool) -> AudioTrackOutput:
    return AudioTrackOutput(
        index=track.index,
        language=track.language.value,
        codec=track.codec,
        channels=track.channels,
        channel_layout=track.channel_layout,
        title=track.title,
        is_default=is_default,
    )


def _to_subtitle_track_output(track: SubtitleTrack) -> SubtitleTrackOutput:
    return SubtitleTrackOutput(
        index=track.index,
        language=track.language.value,
        format=track.format,
        title=track.title,
        is_default=track.is_default,
        is_forced=track.is_forced,
        is_external=track.is_external,
    )


def to_media_file_output(file: MediaFile) -> MediaFileOutput:
    """Convert a MediaFile value object to MediaFileOutput DTO.

    Args:
        file: The domain MediaFile.

    Returns:
        MediaFileOutput with serialized fields.
    """
    # The probe persists ``is_default`` truthfully (container-declared only),
    # so pick the default audio via the ADR-005 selector here too — keeping
    # exactly one default in the output (container default, else first), the
    # same contract the player-facing /tracks projection uses.
    default_audio = TrackSelector().select_audio(file.audio_tracks)
    return MediaFileOutput(
        file_path=file.file_path.value,
        file_size=file.file_size,
        resolution=file.resolution.value,
        video_codec=file.video_codec.value if file.video_codec else None,
        video_bitrate=file.video_bitrate,
        hdr_format=file.hdr_format.value if file.hdr_format else None,
        is_primary=file.is_primary,
        added_at=file.added_at.isoformat(),
        audio_tracks=[
            _to_audio_track_output(t, is_default=t is default_audio) for t in file.audio_tracks
        ],
        subtitle_tracks=[_to_subtitle_track_output(t) for t in file.subtitle_tracks],
    )
