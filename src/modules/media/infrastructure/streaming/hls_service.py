"""HLS segment generation and caching service."""

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)

_SEGMENT_DURATION = 10  # seconds per segment


class HlsService:
    """Generate and cache HLS segments for video files.

    Converts any video format to HLS (m3u8 + ts segments) via FFmpeg.
    Segments are cached in a directory keyed by file path hash,
    so subsequent plays skip the generation step.

    Args:
        cache_dir: Directory to store generated HLS files.
    """

    def __init__(self, cache_dir: str = "./hls_cache") -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_output_dir(self, file_path: str) -> Path:
        """Get the cache directory for a specific video file."""
        path_hash = hashlib.md5(file_path.encode()).hexdigest()
        return self._cache_dir / path_hash

    def get_playlist_path(self, file_path: str) -> Path | None:
        """Get the playlist path if segments exist, None otherwise."""
        output_dir = self._get_output_dir(file_path)
        playlist = output_dir / "playlist.m3u8"
        return playlist if playlist.is_file() else None

    def get_segment_path(self, file_path: str, segment_name: str) -> Path | None:
        """Get a segment file path if it exists."""
        output_dir = self._get_output_dir(file_path)
        segment = output_dir / segment_name
        return segment if segment.is_file() else None

    def generate(self, file_path: str) -> Path:
        """Generate HLS segments for a video file.

        If segments already exist in cache, returns immediately.
        Otherwise runs FFmpeg to create m3u8 + ts segments.

        Args:
            file_path: Absolute path to the source video file.

        Returns:
            Path to the generated playlist.m3u8 file.

        Raises:
            RuntimeError: If FFmpeg is not available or fails.
        """
        output_dir = self._get_output_dir(file_path)
        playlist = output_dir / "playlist.m3u8"

        # Return cached if exists
        if playlist.is_file():
            return playlist

        if not shutil.which("ffmpeg"):
            msg = "FFmpeg is required for HLS streaming but was not found"
            raise RuntimeError(msg)

        source = Path(file_path)
        if not source.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-i",
            file_path,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-hls_time",
            str(_SEGMENT_DURATION),
            "-hls_list_size",
            "0",
            "-hls_segment_filename",
            str(output_dir / "segment_%04d.ts"),
            "-loglevel",
            "error",
            "-y",
            str(playlist),
        ]

        _logger.info("Generating HLS segments for %s", file_path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            # Clean up on failure
            shutil.rmtree(output_dir, ignore_errors=True)
            msg = f"FFmpeg failed: {result.stderr}"
            raise RuntimeError(msg)

        _logger.info("HLS segments generated at %s", output_dir)
        return playlist

    def clear_cache(self, file_path: str | None = None) -> None:
        """Clear cached HLS segments.

        Args:
            file_path: Clear cache for specific file, or all if None.
        """
        if file_path:
            output_dir = self._get_output_dir(file_path)
            shutil.rmtree(output_dir, ignore_errors=True)
        else:
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            self._cache_dir.mkdir(parents=True, exist_ok=True)


__all__ = ["HlsService"]
