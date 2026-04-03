"""Media API request/response schemas."""

from src.modules.media.presentation.schemas.file_variant_schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetPrimaryFileRequest,
)

__all__ = [
    "AddFileVariantRequest",
    "RemoveFileVariantRequest",
    "SetPrimaryFileRequest",
]
