"""Library Management bounded context (re-export for backwards compatibility)."""

from src.modules.library.domain.entities import Library
from src.modules.library.domain.repositories import LibraryRepository
from src.modules.library.domain.services import TrackSelector
from src.modules.library.domain.value_objects import (
    AudioTrack,
    LanguageCode,
    LibraryId,
    LibraryName,
    LibrarySettings,
    LibraryType,
    MetadataProvider,
    MetadataProviderConfig,
    SubtitleMode,
    SubtitleTrack,
)

__all__ = [
    "AudioTrack",
    "LanguageCode",
    "Library",
    "LibraryId",
    "LibraryName",
    "LibraryRepository",
    "LibrarySettings",
    "LibraryType",
    "MetadataProvider",
    "MetadataProviderConfig",
    "SubtitleMode",
    "SubtitleTrack",
    "TrackSelector",
]
