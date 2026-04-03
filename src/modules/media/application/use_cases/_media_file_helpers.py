"""Shared helpers for media file variant use cases."""

from src.modules.media.application.dtos.media_file_dtos import MediaFileOutput
from src.modules.media.domain.value_objects import MediaFile


def to_media_file_output(file: MediaFile) -> MediaFileOutput:
    """Convert a MediaFile value object to MediaFileOutput DTO.

    Args:
        file: The domain MediaFile.

    Returns:
        MediaFileOutput with serialized fields.
    """
    return MediaFileOutput(
        file_path=file.file_path.value,
        file_size=file.file_size,
        resolution=file.resolution.value,
        video_codec=file.video_codec.value if file.video_codec else None,
        video_bitrate=file.video_bitrate,
        hdr_format=file.hdr_format.value if file.hdr_format else None,
        is_primary=file.is_primary,
        added_at=file.added_at.isoformat(),
    )
