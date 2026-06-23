"""Media application ports (interfaces for infrastructure and external BCs)."""

from src.modules.media.application.ports.catalog_request_lookup_port import (
    CatalogRequestLookupPort,
    CatalogRequestStatus,
)
from src.modules.media.application.ports.credits_detector_port import (
    CreditsDetectorPort,
    CreditsDetectorTuning,
    CreditsSignal,
    DetectedCredits,
)
from src.modules.media.application.ports.file_scanner_port import (
    FileSystemScanner,
    MediaType,
    ScannedFile,
)
from src.modules.media.application.ports.file_streamer_port import FileStreamerPort
from src.modules.media.application.ports.hls_playlist_port import (
    HlsCacheStats,
    HlsPlaylistPort,
)
from src.modules.media.application.ports.intro_detector_port import (
    DetectedIntro,
    EpisodeMediaRef,
    IntroDetectionResult,
    IntroDetectorPort,
    IntroDetectorTuning,
)
from src.modules.media.application.ports.media_probe_port import (
    MediaProbePort,
    ProbeResult,
)
from src.modules.media.application.ports.metadata_provider_port import (
    CollectionDetailMetadata,
    CollectionMetadata,
    CollectionPartMetadata,
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    MediaMetadata,
    MetadataProvider,
    PersonMetadata,
    SearchCandidate,
    SeasonMetadata,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.ports.progress_lookup_port import (
    ProgressLookupPort,
    ProgressSummary,
)
from src.modules.media.application.ports.scheduler_control_port import (
    SchedulerControlPort,
)
from src.modules.media.application.ports.scheduler_inspector_port import (
    ScheduledJob,
    SchedulerInspectorPort,
    SchedulerSnapshot,
)
from src.modules.media.application.ports.scrub_preview_locator_port import (
    ScrubPreviewLocatorPort,
)
from src.modules.media.application.ports.variant_detector_port import (
    VariantDetectorPort,
)

__all__ = [
    "CatalogRequestLookupPort",
    "CatalogRequestStatus",
    "CollectionDetailMetadata",
    "CollectionMetadata",
    "CollectionPartMetadata",
    "CreditPerson",
    "CreditsDetectorPort",
    "CreditsDetectorTuning",
    "CreditsSignal",
    "DetectedCredits",
    "DetectedIntro",
    "EpisodeMediaRef",
    "EpisodeMetadata",
    "FileStreamerPort",
    "FileSystemScanner",
    "HlsCacheStats",
    "HlsPlaylistPort",
    "IntroDetectionResult",
    "IntroDetectorPort",
    "IntroDetectorTuning",
    "LocalizedFields",
    "MediaMetadata",
    "MediaProbePort",
    "MediaType",
    "MetadataProvider",
    "PersonMetadata",
    "ProbeResult",
    "ProfileLibraryAccessPort",
    "ProgressLookupPort",
    "ProgressSummary",
    "ScannedFile",
    "ScheduledJob",
    "SchedulerControlPort",
    "SchedulerInspectorPort",
    "SchedulerSnapshot",
    "ScrubPreviewLocatorPort",
    "SearchCandidate",
    "SeasonMetadata",
    "VariantDetectorPort",
]
