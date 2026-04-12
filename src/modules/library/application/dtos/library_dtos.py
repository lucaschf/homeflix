"""DTOs for Library CRUD use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Shared output shapes ─────────────────────────────────────────


@dataclass(frozen=True)
class MetadataProviderOutput:
    """One entry in the library's metadata-provider chain."""

    provider: str
    priority: int
    enabled: bool


@dataclass(frozen=True)
class LibrarySettingsOutput:
    """Flattened playback / scan settings for one library."""

    preferred_audio_language: str
    preferred_subtitle_language: str | None
    subtitle_mode: str
    generate_thumbnails: bool
    detect_intros: bool
    auto_refresh_metadata: bool


@dataclass(frozen=True)
class LibraryOutput:
    """Full representation of a library — used by get, list, create, update."""

    id: str
    name: str
    library_type: str
    paths: list[str]
    language: str
    metadata_providers: list[MetadataProviderOutput]
    scan_schedule: str | None
    settings: LibrarySettingsOutput


# ── Create ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreateLibraryInput:
    """Input for ``CreateLibraryUseCase``."""

    name: str
    library_type: str
    paths: list[str]
    language: str = "en"
    metadata_providers: list[dict[str, Any]] = field(default_factory=list)
    scan_schedule: str | None = None
    settings: dict[str, Any] | None = None


# ── Update ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UpdateLibraryInput:
    """Input for ``UpdateLibraryUseCase``.

    All fields except ``library_id`` are optional — only supplied
    fields are updated; omitted fields keep their current value.
    """

    library_id: str
    name: str | None = None
    library_type: str | None = None
    paths: list[str] | None = None
    language: str | None = None
    metadata_providers: list[dict[str, Any]] | None = None
    scan_schedule: str | None = None
    settings: dict[str, Any] | None = None


# ── Delete ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeleteLibraryInput:
    """Input for ``DeleteLibraryUseCase``."""

    library_id: str


# ── Get by ID ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class GetLibraryByIdInput:
    """Input for ``GetLibraryByIdUseCase``."""

    library_id: str


__all__ = [
    "CreateLibraryInput",
    "DeleteLibraryInput",
    "GetLibraryByIdInput",
    "LibraryOutput",
    "LibrarySettingsOutput",
    "MetadataProviderOutput",
    "UpdateLibraryInput",
]
