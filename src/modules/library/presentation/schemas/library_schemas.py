"""Pydantic schemas for Library REST API request/response validation."""

from pydantic import BaseModel, Field


class MetadataProviderSchema(BaseModel):
    """One entry in the metadata-provider chain."""

    provider: str = Field(description="Provider name: tmdb, omdb, or tvdb")
    priority: int = Field(ge=1, le=10, default=1)
    enabled: bool = True


class LibrarySettingsSchema(BaseModel):
    """Playback / scan settings for a library."""

    preferred_audio_language: str = "en"
    preferred_subtitle_language: str | None = None
    subtitle_mode: str = "foreign"
    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False


class CreateLibraryRequest(BaseModel):
    """POST /api/v1/libraries body."""

    name: str = Field(min_length=1, max_length=200)
    library_type: str = Field(description="movies, series, or mixed")
    paths: list[str] = Field(min_length=1)
    language: str = "en"
    metadata_providers: list[MetadataProviderSchema] = Field(default_factory=list)
    scan_schedule: str | None = None
    settings: LibrarySettingsSchema | None = None


class UpdateLibraryRequest(BaseModel):
    """PUT /api/v1/libraries/{library_id} body.

    All fields are optional — only supplied fields are updated.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    library_type: str | None = None
    paths: list[str] | None = None
    language: str | None = None
    metadata_providers: list[MetadataProviderSchema] | None = None
    scan_schedule: str | None = None
    settings: LibrarySettingsSchema | None = None


__all__ = [
    "CreateLibraryRequest",
    "LibrarySettingsSchema",
    "MetadataProviderSchema",
    "UpdateLibraryRequest",
]
