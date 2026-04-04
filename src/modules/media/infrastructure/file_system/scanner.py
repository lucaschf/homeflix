"""Filesystem scanner for discovering media files."""

import re
from pathlib import Path, PurePath

from src.modules.media.application.ports import FileSystemScanner, MediaType, ScannedFile
from src.shared_kernel.value_objects.file_path import FilePath

_SUPPORTED_EXTENSIONS = frozenset({".mp4", ".mkv", ".avi", ".mov", ".wmv"})

# Episode patterns: S01E01, s01e01, 1x01
_EPISODE_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})"),
    re.compile(r"(\d{1,2})[Xx](\d{2})"),
]

# Season folder patterns: "Season 01", "Season 1", "S01"
_SEASON_FOLDER_PATTERN = re.compile(r"^(?:[Ss]eason\s*(\d{1,2})|[Ss](\d{1,2}))$")

# Year in filename: (2010), .2010., _2010_
_YEAR_PATTERN = re.compile(r"[\.\s_\-\(]?((?:19|20)\d{2})[\.\s_\-\)]?")

# Resolution patterns
_RESOLUTION_MAP = {
    re.compile(r"2160[pi]|4[Kk]|UHD", re.IGNORECASE): "4K",
    re.compile(r"1080[pi]|[Ff]ull\s*[Hh][Dd]|FHD", re.IGNORECASE): "1080p",
    re.compile(r"720[pi]", re.IGNORECASE): "720p",
    re.compile(r"480[pi]", re.IGNORECASE): "480p",
    re.compile(r"360[pi]", re.IGNORECASE): "360p",
}


def _extract_resolution(filename: str) -> str | None:
    """Extract resolution from filename."""
    for pattern, name in _RESOLUTION_MAP.items():
        if pattern.search(filename):
            return name
    return None


def _extract_year(filename: str) -> int | None:
    """Extract a 4-digit year from filename."""
    match = _YEAR_PATTERN.search(filename)
    return int(match.group(1)) if match else None


def _extract_title(filename: str, year: int | None) -> str:
    """Extract title from filename by removing year and quality tags."""
    stem = PurePath(filename).stem

    # Remove everything from year onwards (if present)
    if year:
        idx = stem.find(str(year))
        if idx > 0:
            stem = stem[:idx]

    # Replace dots, underscores with spaces and strip
    title = re.sub(r"[\._]", " ", stem).strip()
    title = re.sub(r"\s+", " ", title)
    return title.strip(" -")


def _detect_episode(file_path: str) -> tuple[str, int, int] | None:
    """Detect episode info from file path.

    Returns:
        Tuple of (series_name, season_number, episode_number), or None.
    """
    filename = Path(file_path).name

    # Try episode pattern in filename
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            series_name = _find_series_name(file_path)
            return (series_name, season_num, episode_num)

    return None


def _find_series_name(file_path: str) -> str:
    """Find series name from directory structure.

    Walks up the directory tree looking for the series root folder.
    """
    parts = PurePath(file_path).parts

    for i, part in enumerate(parts):
        # Check if this folder is a season folder
        if _SEASON_FOLDER_PATTERN.match(part) and i > 0:
            return parts[i - 1]

    # Fallback: if no season folder found, use grandparent of file
    if len(parts) >= 3:
        return parts[-3]

    # Last resort: extract from filename before SxxExx
    filename = Path(file_path).name
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            title = filename[: match.start()]
            return re.sub(r"[\._]", " ", title).strip(" -")

    return "Unknown Series"


class LocalFileSystemScanner(FileSystemScanner):
    """Scan local directories for media files.

    Walks directories recursively, identifies supported video files,
    and classifies them as movies or episodes based on naming patterns.

    Example:
        >>> scanner = LocalFileSystemScanner()
        >>> files = scanner.scan_directories([FilePath("/media/movies")])
    """

    def scan_directories(self, directories: list[FilePath]) -> list[ScannedFile]:
        """Scan directories recursively for media files.

        Args:
            directories: List of directory paths to scan.

        Returns:
            List of discovered media files with parsed metadata.
        """
        results: list[ScannedFile] = []

        for directory in directories:
            dir_path = Path(directory.value)
            if not dir_path.is_dir():
                continue

            for path in dir_path.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                    continue

                full_path = str(path)
                file_size = path.stat().st_size
                resolution = _extract_resolution(path.name)
                episode_info = _detect_episode(full_path)

                if episode_info:
                    series_name, season_num, episode_num = episode_info
                    results.append(
                        ScannedFile(
                            file_path=FilePath(full_path),
                            file_size=file_size,
                            media_type=MediaType.EPISODE,
                            title=series_name,
                            resolution=resolution,
                            series_name=series_name,
                            season_number=season_num,
                            episode_number=episode_num,
                        ),
                    )
                else:
                    year = _extract_year(path.name)
                    title = _extract_title(path.name, year)
                    results.append(
                        ScannedFile(
                            file_path=FilePath(full_path),
                            file_size=file_size,
                            media_type=MediaType.MOVIE,
                            title=title,
                            year=year,
                            resolution=resolution,
                        ),
                    )

        return results


__all__ = ["LocalFileSystemScanner"]
