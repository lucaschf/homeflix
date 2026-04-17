"""Pydantic schemas for media scan endpoints."""

from pydantic import BaseModel, Field


class ScanMediaRequest(BaseModel):
    """Request body for triggering a media scan."""

    directories: list[str] = Field(
        default_factory=list,
        description="Directories to scan. If empty, uses configured media_directories.",
    )


__all__ = ["ScanMediaRequest"]
