"""Library Management bounded context.

This context handles library configuration including:
- Library entity with scan and playback settings
- Metadata provider configuration
- Audio and subtitle track preferences
"""

from src.domain.library.entities.library import Library
from src.domain.library.repositories.library_repository import LibraryRepository
from src.domain.library.services.track_selector import TrackSelector
from src.domain.library.value_objects.language_code import LanguageCode
from src.domain.library.value_objects.library_id import LibraryId
from src.domain.library.value_objects.library_name import LibraryName
from src.domain.library.value_objects.library_settings import LibrarySettings
from src.domain.library.value_objects.library_type import LibraryType
from src.domain.library.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)
from src.domain.library.value_objects.subtitle_mode import SubtitleMode
from src.domain.library.value_objects.tracks import AudioTrack, SubtitleTrack

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
