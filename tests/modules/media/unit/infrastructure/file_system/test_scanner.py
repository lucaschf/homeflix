"""Unit tests for LocalFileSystemScanner."""

from pathlib import Path

import pytest

from src.modules.media.application.ports import MediaType
from src.modules.media.infrastructure.file_system.scanner import LocalFileSystemScanner
from src.shared_kernel.value_objects.file_path import FilePath


@pytest.fixture  # type: ignore[misc]
def scanner() -> LocalFileSystemScanner:
    """Create a scanner instance."""
    return LocalFileSystemScanner()


@pytest.fixture  # type: ignore[misc]
def media_dir(tmp_path: Path) -> Path:
    """Create a temporary media directory with test files."""
    return tmp_path


def _create_file(directory: Path, name: str, size: int = 1024) -> Path:
    """Helper to create a file with specific size."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


@pytest.mark.unit
class TestScanDirectories:
    """Tests for LocalFileSystemScanner.scan_directories()."""

    def test_should_find_movie_files(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir, "Inception.2010.1080p.BluRay.mkv")
        _create_file(media_dir, "Interstellar.2014.4K.mp4")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 2
        assert all(r.media_type == MediaType.MOVIE for r in results)

    def test_should_filter_unsupported_extensions(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir, "movie.mkv")
        _create_file(media_dir, "subtitle.srt")
        _create_file(media_dir, "poster.jpg")
        _create_file(media_dir, "readme.txt")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 1
        assert results[0].file_path.value.endswith(".mkv")

    def test_should_detect_episode_pattern_sxxexx(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        show_dir = media_dir / "Breaking Bad" / "Season 01"
        _create_file(show_dir, "Breaking.Bad.S01E01.1080p.mkv")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 1
        assert results[0].media_type == MediaType.EPISODE
        assert results[0].series_name == "Breaking Bad"
        assert results[0].season_number == 1
        assert results[0].episode_number == 1

    def test_should_detect_episode_pattern_nxnn(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        show_dir = media_dir / "Friends" / "Season 02"
        _create_file(show_dir, "Friends.2x05.720p.mkv")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 1
        assert results[0].media_type == MediaType.EPISODE
        assert results[0].season_number == 2
        assert results[0].episode_number == 5

    def test_should_extract_movie_title_and_year(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir, "Inception.2010.1080p.BluRay.mkv")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert results[0].title == "Inception"
        assert results[0].year == 2010

    def test_should_extract_resolution(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir, "movie.4K.mkv")
        _create_file(media_dir, "movie.1080p.mkv")
        _create_file(media_dir, "movie.720p.mkv")

        results = scanner.scan_directories([FilePath(str(media_dir))])
        resolutions = {r.resolution for r in results}

        assert resolutions == {"4K", "1080p", "720p"}

    def test_should_report_file_size(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir, "movie.mkv", size=4096)

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert results[0].file_size == 4096

    def test_should_scan_nested_directories(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        _create_file(media_dir / "action", "movie1.mkv")
        _create_file(media_dir / "comedy", "movie2.mp4")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 2

    def test_should_handle_empty_directory(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert results == []

    def test_should_skip_nonexistent_directory(
        self,
        scanner: LocalFileSystemScanner,
    ) -> None:
        results = scanner.scan_directories([FilePath("/nonexistent/path")])

        assert results == []

    def test_should_scan_multiple_directories(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        dir1 = media_dir / "movies"
        dir2 = media_dir / "series"
        _create_file(dir1, "movie.mkv")
        _create_file(dir2 / "show" / "Season 01", "show.S01E01.mkv")

        results = scanner.scan_directories(
            [
                FilePath(str(dir1)),
                FilePath(str(dir2)),
            ]
        )

        assert len(results) == 2
        types = {r.media_type for r in results}
        assert types == {MediaType.MOVIE, MediaType.EPISODE}

    def test_should_support_all_video_extensions(
        self, scanner: LocalFileSystemScanner, media_dir: Path
    ) -> None:
        for ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv"]:
            _create_file(media_dir, f"movie{ext}")

        results = scanner.scan_directories([FilePath(str(media_dir))])

        assert len(results) == 5
