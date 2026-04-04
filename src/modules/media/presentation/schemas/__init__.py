"""Media API request/response schemas."""

from src.modules.media.presentation.schemas.file_variant_schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetPrimaryFileRequest,
)
from src.modules.media.presentation.schemas.scan_schemas import (
    ScanMediaRequest,
    ScanMediaResponse,
)

__all__ = [
    "AddFileVariantRequest",
    "RemoveFileVariantRequest",
    "ScanMediaRequest",
    "ScanMediaResponse",
    "SetPrimaryFileRequest",
]
