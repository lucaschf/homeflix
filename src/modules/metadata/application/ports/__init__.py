"""Metadata application ports (the module's published provider contract)."""

from src.modules.metadata.application.ports.artwork_downloader_port import (
    ALLOWED_ARTWORK_HOSTS,
    ArtworkDownloaderPort,
    DownloadedImage,
)
from src.modules.metadata.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)
from src.modules.metadata.application.ports.metadata_provider_port import (
    CollectionDetailMetadata,
    CollectionMetadata,
    CollectionPartMetadata,
    CreditPerson,
    EpisodeMetadata,
    LocalizedFields,
    LocalizedTextFields,
    MediaMetadata,
    MetadataProvider,
    PersonMetadata,
    SearchCandidate,
    SeasonMetadata,
)

__all__ = [
    "ALLOWED_ARTWORK_HOSTS",
    "ArtworkDownloaderPort",
    "ArtworkStoragePort",
    "CollectionDetailMetadata",
    "CollectionMetadata",
    "CollectionPartMetadata",
    "CreditPerson",
    "DownloadedImage",
    "EpisodeMetadata",
    "LocalizedFields",
    "LocalizedTextFields",
    "MediaMetadata",
    "MetadataProvider",
    "PersonMetadata",
    "SearchCandidate",
    "SeasonMetadata",
    "StoredArtwork",
]
