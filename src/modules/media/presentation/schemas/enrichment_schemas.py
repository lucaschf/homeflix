"""Pydantic schemas for metadata enrichment endpoints."""

from pydantic import BaseModel, Field


class EnrichRequest(BaseModel):
    """Request body for metadata enrichment."""

    force: bool = Field(
        default=False,
        description="Re-enrich even if metadata already exists.",
    )


class EnrichResponse(BaseModel):
    """Response body for single media enrichment."""

    media_id: str
    enriched: bool
    provider: str | None = None
    error: str | None = None


class BulkEnrichResponse(BaseModel):
    """Response body for bulk metadata enrichment."""

    movies_enriched: int
    series_enriched: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


__all__ = ["BulkEnrichResponse", "EnrichRequest", "EnrichResponse"]
