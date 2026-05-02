"""Media application ports (interfaces for infrastructure and external BCs)."""

from src.modules.media.application.ports.file_scanner_port import (
    FileSystemScanner,
    MediaType,
    ScannedFile,
)
from src.modules.media.application.ports.file_streamer_port import FileStreamerPort
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.ports.intro_detector_port import (
    DetectedIntro,
    EpisodeFingerprint,
    IntroDetectorPort,
)
from src.modules.media.application.ports.media_probe_port import (
    MediaProbePort,
    ProbeResult,
)
from src.modules.media.application.ports.metadata_provider_port import (
    CollectionMetadata,
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    MediaMetadata,
    MetadataProvider,
    PersonMetadata,
    SeasonMetadata,
)
from src.modules.media.application.ports.progress_lookup_port import (
    ProgressLookupPort,
    ProgressSummary,
)
from src.modules.media.application.ports.variant_detector_port import (
    VariantDetectorPort,
)

__all__ = [
    "CollectionMetadata",
    "CreditPerson",
    "DetectedIntro",
    "EpisodeFingerprint",
    "EpisodeMetadata",
    "FileStreamerPort",
    "FileSystemScanner",
    "HlsPlaylistPort",
    "IntroDetectorPort",
    "LocalizedFields",
    "MediaMetadata",
    "MediaProbePort",
    "MediaType",
    "MetadataProvider",
    "PersonMetadata",
    "ProbeResult",
    "ProgressLookupPort",
    "ProgressSummary",
    "ScannedFile",
    "SeasonMetadata",
    "VariantDetectorPort",
]
