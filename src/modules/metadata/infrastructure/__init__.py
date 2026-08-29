"""Metadata infrastructure adapters (TMDB gateway + artwork mirror)."""

from src.modules.metadata.infrastructure.artwork_downloader import HttpxArtworkDownloader
from src.modules.metadata.infrastructure.local_artwork_storage import LocalArtworkStorage
from src.modules.metadata.infrastructure.tmdb_client import TmdbClient

__all__ = ["HttpxArtworkDownloader", "LocalArtworkStorage", "TmdbClient"]
