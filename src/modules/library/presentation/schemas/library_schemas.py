"""Pydantic schemas for Library REST API request/response validation."""

from pydantic import BaseModel, Field

from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)


class MetadataProviderSchema(BaseModel):
    """One entry in the metadata-provider chain."""

    provider: str = Field(description="Provider name: tmdb, omdb, or tvdb")
    priority: int = Field(ge=1, le=10, default=1)
    enabled: bool = True

    def to_config(self) -> MetadataProviderConfig:
        """Convert the request shape into the domain value object."""
        return MetadataProviderConfig(
            provider=MetadataProvider(self.provider),
            priority=self.priority,
            enabled=self.enabled,
        )


class LibrarySettingsSchema(BaseModel):
    """Scan settings for a library.

    Playback preferences (audio/subtitle language, subtitle mode) are
    per-user in the Preferences BC, not per-library (ADR-026).
    """

    generate_thumbnails: bool = True
    detect_intros: bool = False
    auto_refresh_metadata: bool = False

    def to_settings(self) -> LibrarySettings:
        """Convert the request shape into the domain value object."""
        return LibrarySettings(
            generate_thumbnails=self.generate_thumbnails,
            detect_intros=self.detect_intros,
            auto_refresh_metadata=self.auto_refresh_metadata,
        )


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
