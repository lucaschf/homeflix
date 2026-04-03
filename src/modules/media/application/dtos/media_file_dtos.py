"""MediaFile DTOs for file variant operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaFileOutput:
    """Output representation of a MediaFile variant.

    Attributes:
        file_path: Absolute path to the video file.
        file_size: File size in bytes.
        resolution: Video resolution name (e.g., "1080p", "4K").
        video_codec: Video codec (e.g., "h265").
        video_bitrate: Video bitrate in kbps.
        hdr_format: HDR format if applicable.
        is_primary: Whether this is the primary file variant.
        added_at: ISO timestamp of when the file was registered.
    """

    file_path: str
    file_size: int
    resolution: str
    video_codec: str | None
    video_bitrate: int | None
    hdr_format: str | None
    is_primary: bool
    added_at: str


@dataclass(frozen=True)
class AddFileVariantInput:
    """Input for adding a file variant to a media entity.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
        file_path: Absolute path to the video file.
        file_size: File size in bytes.
        resolution: Video resolution name.
        video_codec: Video codec.
        video_bitrate: Video bitrate in kbps.
        hdr_format: HDR format if applicable.
        is_primary: Whether to set as primary variant.
    """

    media_id: str
    file_path: str
    file_size: int
    resolution: str
    video_codec: str | None = None
    video_bitrate: int | None = None
    hdr_format: str | None = None
    is_primary: bool = False


@dataclass(frozen=True)
class RemoveFileVariantInput:
    """Input for removing a file variant from a media entity.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
        file_path: Path of the file variant to remove.
    """

    media_id: str
    file_path: str


@dataclass(frozen=True)
class SetPrimaryFileInput:
    """Input for setting a file variant as primary.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
        file_path: Path of the file variant to set as primary.
    """

    media_id: str
    file_path: str


@dataclass(frozen=True)
class GetFileVariantsInput:
    """Input for listing file variants of a media entity.

    Attributes:
        media_id: External ID of the media (mov_xxx or epi_xxx).
    """

    media_id: str


__all__ = [
    "AddFileVariantInput",
    "GetFileVariantsInput",
    "MediaFileOutput",
    "RemoveFileVariantInput",
    "SetPrimaryFileInput",
]
