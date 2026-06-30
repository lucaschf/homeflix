"""DTOs for Library CRUD use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.library.domain.value_objects.library_settings import LibrarySettings
    from src.modules.library.domain.value_objects.metadata_provider import (
        MetadataProviderConfig,
    )

# ── Shared output shapes ─────────────────────────────────────────


@dataclass(frozen=True)
class MetadataProviderOutput:
    """One entry in the library's metadata-provider chain."""

    provider: str
    priority: int
    enabled: bool


@dataclass(frozen=True)
class LibrarySettingsOutput:
    """Flattened scan settings for one library.

    Playback preferences live in the Preferences BC (per-user), not here
    (ADR-026).
    """

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
    last_scan_at: str | None
    movie_count: int
    series_count: int
    settings: LibrarySettingsOutput


# ── Create ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreateLibraryInput:
    """Input for ``CreateLibraryUseCase``."""

    name: str
    library_type: str
    paths: list[str]
    language: str = "en"
    metadata_providers: list[MetadataProviderConfig] = field(default_factory=list)
    scan_schedule: str | None = None
    settings: LibrarySettings | None = None


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
    metadata_providers: list[MetadataProviderConfig] | None = None
    scan_schedule: str | None = None
    settings: LibrarySettings | None = None


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
