"""Media API request/response schemas."""

from src.modules.media.presentation.schemas.enrichment_schemas import (
    BulkEnrichResponse,
    EnrichRequest,
    EnrichResponse,
)
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
    "BulkEnrichResponse",
    "EnrichRequest",
    "EnrichResponse",
    "RemoveFileVariantRequest",
    "ScanMediaRequest",
    "ScanMediaResponse",
    "SetPrimaryFileRequest",
]
