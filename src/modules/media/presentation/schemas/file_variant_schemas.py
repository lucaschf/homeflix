"""Request schemas for file variant endpoints."""

from pydantic import BaseModel


class AddFileVariantRequest(BaseModel):
    """Request body for adding a file variant.

    Attributes:
        file_path: Absolute path to the video file.
        file_size: File size in bytes.
        resolution: Video resolution name (e.g., "1080p", "4K").
        video_codec: Video codec (e.g., "h265").
        video_bitrate: Video bitrate in kbps.
        hdr_format: HDR format if applicable.
        is_primary: Whether to set as primary variant.
    """

    file_path: str
    file_size: int
    resolution: str
    video_codec: str | None = None
    video_bitrate: int | None = None
    hdr_format: str | None = None
    is_primary: bool = False


class RemoveFileVariantRequest(BaseModel):
    """Request body for removing a file variant.

    Attributes:
        file_path: Path of the file variant to remove.
    """

    file_path: str


class SetPrimaryFileRequest(BaseModel):
    """Request body for setting the primary file.

    Attributes:
        file_path: Path of the file variant to set as primary.
    """

    file_path: str


__all__ = [
    "AddFileVariantRequest",
    "RemoveFileVariantRequest",
    "SetPrimaryFileRequest",
]
