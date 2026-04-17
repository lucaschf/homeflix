"""Media API request/response schemas."""

from src.modules.media.presentation.schemas.enrichment_schemas import EnrichRequest
from src.modules.media.presentation.schemas.file_variant_schemas import (
    AddFileVariantRequest,
    RemoveFileVariantRequest,
    SetPrimaryFileRequest,
)
from src.modules.media.presentation.schemas.scan_schemas import ScanMediaRequest

__all__ = [
    "AddFileVariantRequest",
    "EnrichRequest",
    "RemoveFileVariantRequest",
    "ScanMediaRequest",
    "SetPrimaryFileRequest",
]
