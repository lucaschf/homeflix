"""Pydantic schemas for preferences REST API."""

from typing import Literal

from pydantic import BaseModel, Field


class SubtitleAppearanceRequest(BaseModel):
    """Partial subtitle-styling update. Any subset of the knobs."""

    color: str | None = None
    background: str | None = None
    font_size: Literal["small", "medium", "large"] | None = None
    text_edge: Literal["none", "shadow", "outline"] | None = None


class UpdatePreferencesRequest(BaseModel):
    """PUT /api/v1/preferences body. All fields optional."""

    audio_lang: str | None = None
    subtitle_lang: str | None = None
    subtitle_mode: str | None = None
    default_quality: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    subtitle_appearance: SubtitleAppearanceRequest | None = None


__all__ = ["SubtitleAppearanceRequest", "UpdatePreferencesRequest"]
