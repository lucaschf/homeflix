"""Pydantic schemas for metadata enrichment endpoints."""

from pydantic import BaseModel, Field


class EnrichRequest(BaseModel):
    """Request body for metadata enrichment."""

    force: bool = Field(
        default=False,
        description="Re-enrich even if metadata already exists.",
    )


__all__ = ["EnrichRequest"]
