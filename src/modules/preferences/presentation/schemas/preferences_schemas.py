"""Pydantic schemas for preferences REST API."""

from pydantic import BaseModel, Field


class UpdatePreferencesRequest(BaseModel):
    """PUT /api/v1/preferences body. All fields optional."""

    audio_lang: str | None = None
    subtitle_lang: str | None = None
    subtitle_mode: str | None = None
    default_quality: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)


__all__ = ["UpdatePreferencesRequest"]
