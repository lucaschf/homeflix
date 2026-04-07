"""HLS segment generation and caching service.

Supports progressive playback: FFmpeg runs in the background and
the playlist is returned as soon as the first segments are ready.
hls.js treats a playlist without ``#EXT-X-ENDLIST`` as a live stream
and keeps polling for new segments until the tag appears.
"""

import asyncio
import hashlib
import logging
import shutil
import subprocess
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

_SEGMENT_DURATION = 10  # seconds per segment
_POLL_INTERVAL = 0.5  # seconds between readiness checks
_POLL_TIMEOUT = 120  # max seconds to wait for first segment
_BROWSER_SAFE_CODECS = {"h264", "mpeg4", "mpeg2video"}


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
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    def get_path_hash(self, file_path: str) -> str:
        """Get the hash key for a file path."""
        return hashlib.md5(file_path.encode()).hexdigest()

    def _get_output_dir(self, file_path: str) -> Path:
        """Get the cache directory for a specific video file."""
        return self._cache_dir / self.get_path_hash(file_path)

    def get_segment_by_hash(self, path_hash: str, segment_name: str) -> Path | None:
        """Get a segment file by its path hash, without needing the original file path."""
        segment = self._cache_dir / path_hash / segment_name
        return segment if segment.is_file() else None

    def is_complete(self, path_hash: str) -> bool:
        """Check if generation is fully complete (playlist has ENDLIST tag)."""
        playlist = self._cache_dir / path_hash / "playlist.m3u8"
        if not playlist.is_file():
            return False
        try:
            return "#EXT-X-ENDLIST" in playlist.read_text(encoding="utf-8")
        except OSError:
            return False

    def get_playlist_content(self, path_hash: str) -> str | None:
        """Get current playlist content, or None if not ready yet."""
        playlist = self._cache_dir / path_hash / "playlist.m3u8"
        if not playlist.is_file():
            return None
        try:
            return playlist.read_text(encoding="utf-8")
        except OSError:
            return None

    @staticmethod
    def _probe_video_codec(file_path: str) -> str | None:
        """Detect video codec using ffprobe.

        Args:
            file_path: Already-validated absolute path to the source file.
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            codec = result.stdout.strip().lower()
            return codec if codec else None
        except Exception:
            return None

    def _build_ffmpeg_cmd(self, file_path: str, output_dir: Path) -> list[str]:
        """Build FFmpeg command, transcoding to H.264 if needed."""
        codec = self._probe_video_codec(file_path)
        needs_transcode = codec not in _BROWSER_SAFE_CODECS

        if needs_transcode:
            _logger.info(
                "Source codec is %s — transcoding to H.264 for %s",
                codec,
                file_path,
            )
            video_args = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
        else:
            _logger.info("Source codec is %s — copying for %s", codec, file_path)
            video_args = ["-c:v", "copy"]

        return [
            "ffmpeg",
            "-i",
            file_path,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-sn",
            *video_args,
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-hls_time",
            str(_SEGMENT_DURATION),
            "-hls_list_size",
            "0",
            "-hls_playlist_type",
            "event",
            "-hls_segment_filename",
            str(output_dir / "segment_%04d.ts"),
            "-loglevel",
            "error",
            "-y",
            str(output_dir / "playlist.m3u8"),
        ]

    @staticmethod
    def _validate_source(file_path: str) -> Path:
        """Resolve and validate that file_path is an existing file.

        Prevents path traversal and ensures the subprocess only
        receives a resolved absolute path to a real file.

        Raises:
            FileNotFoundError: If path does not point to an existing file.
        """
        resolved = Path(file_path).resolve()
        if not resolved.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)
        return resolved

    def _start_ffmpeg(self, file_path: str) -> str:
        """Start FFmpeg in background if not already running.

        Returns:
            The path hash for this file.
        """
        source = self._validate_source(file_path)
        safe_path = str(source)
        path_hash = self.get_path_hash(file_path)

        with self._lock:
            # Already complete
            if self.is_complete(path_hash):
                return path_hash

            # Already running
            if path_hash in self._processes:
                proc = self._processes[path_hash]
                if proc.poll() is None:
                    return path_hash
                # Process finished (maybe with error) — clean up handle
                del self._processes[path_hash]

            # Clean up stale incomplete cache from a previous run
            output_dir = self._cache_dir / path_hash
            if output_dir.exists():
                _logger.info("Cleaning stale cache for %s", path_hash)
                shutil.rmtree(output_dir, ignore_errors=True)

            output_dir.mkdir(parents=True, exist_ok=True)

            cmd = self._build_ffmpeg_cmd(safe_path, output_dir)

            _logger.info("Starting HLS generation for %s", safe_path)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._processes[path_hash] = proc

        return path_hash

    async def ensure_playlist(self, file_path: str) -> str:
        """Start generation and wait until the playlist has at least one segment.

        For already-cached files this returns immediately. Otherwise
        FFmpeg is launched in the background and we poll until the
        m3u8 file appears with at least one segment entry.

        Args:
            file_path: Absolute path to the source video file.

        Returns:
            The path hash for this file.

        Raises:
            RuntimeError: If FFmpeg is not available, fails, or times out.
            FileNotFoundError: If the source file does not exist.
        """
        path_hash = self.get_path_hash(file_path)

        # Fast path: already fully generated
        if self.is_complete(path_hash):
            return path_hash

        if not shutil.which("ffmpeg"):
            msg = "FFmpeg is required for HLS streaming but was not found"
            raise RuntimeError(msg)

        source = Path(file_path)
        if not source.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)

        await asyncio.to_thread(self._start_ffmpeg, file_path)

        # Poll until playlist has at least one segment
        attempts = int(_POLL_TIMEOUT / _POLL_INTERVAL)
        for _ in range(attempts):
            content = self.get_playlist_content(path_hash)
            if content and "segment_" in content:
                return path_hash

            # Check if process died
            with self._lock:
                proc = self._processes.get(path_hash)
            if proc and proc.poll() is not None:
                stderr = proc.stderr.read().decode() if proc.stderr else ""
                _logger.error("FFmpeg exited with code %d: %s", proc.returncode, stderr)
                # Clean up failed output
                output_dir = self._cache_dir / path_hash
                shutil.rmtree(output_dir, ignore_errors=True)
                msg = f"FFmpeg failed (exit {proc.returncode}): {stderr}"
                raise RuntimeError(msg)

            await asyncio.sleep(_POLL_INTERVAL)

        msg = f"Timeout waiting for HLS segments ({_POLL_TIMEOUT}s)"
        raise RuntimeError(msg)

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
