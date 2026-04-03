"""Dependency injection containers.

This package organizes DI containers per bounded context:
- infrastructure: Database, external clients
- media: Media module repositories and use cases
- library: Library module services and repositories

The main ApplicationContainer composes all sub-containers.
"""

from src.config.containers.library import LibraryContainer
from src.config.containers.main import ApplicationContainer
from src.config.containers.media import MediaContainer

__all__ = [
    "ApplicationContainer",
    "LibraryContainer",
    "MediaContainer",
]
