"""Port for filesystem scanning operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from src.shared_kernel.value_objects.file_path import FilePath


class MediaType(Enum):
    """Classification of a scanned media file."""

    MOVIE = "movie"
    EPISODE = "episode"


@dataclass(frozen=True)
class ScannedFile:
    """A media file discovered during directory scanning.

    Attributes:
        file_path: Absolute path to the media file.
        file_size: File size in bytes.
        media_type: Whether the file is a movie or episode.
        title: Parsed title (movie title or series name).
        year: Parsed year from filename, if present.
        resolution: Parsed resolution from filename, if present.
        series_name: Name of the series (episode only).
        season_number: Season number (episode only).
        episode_number: Episode number (episode only).
    """

    file_path: FilePath
    file_size: int
    media_type: MediaType
    title: str
    year: int | None = None
    resolution: str | None = None
    series_name: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None


class FileSystemScanner(ABC):
    """Port for scanning directories for media files."""

    @abstractmethod
    def scan_directories(self, directories: list[FilePath]) -> list[ScannedFile]:
        """Scan directories recursively for media files.

        Args:
            directories: List of directory paths to scan.

        Returns:
            List of discovered media files with parsed metadata.
        """
        ...


__all__ = ["FileSystemScanner", "MediaType", "ScannedFile"]
