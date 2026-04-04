"""Pydantic schemas for media scan endpoints."""

from pydantic import BaseModel, Field


class ScanMediaRequest(BaseModel):
    """Request body for triggering a media scan."""

    directories: list[str] = Field(
        default_factory=list,
        description="Directories to scan. If empty, uses configured media_directories.",
    )


class ScanMediaResponse(BaseModel):
    """Response body for a completed media scan."""

    movies_created: int
    movies_updated: int
    episodes_created: int
    episodes_updated: int
    errors: list[str] = Field(default_factory=list)


__all__ = ["ScanMediaRequest", "ScanMediaResponse"]
