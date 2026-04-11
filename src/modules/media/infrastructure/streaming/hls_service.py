"""HLS segment generation and caching service.

Supports progressive playback: FFmpeg runs in the background and
the playlist is returned as soon as the first segments are ready.
hls.js treats a playlist without ``#EXT-X-ENDLIST`` as a live stream
and keeps polling for new segments until the tag appears.

Multi-track support generates a master playlist with separate audio
renditions and WebVTT subtitle tracks via ``#EXT-X-MEDIA`` tags.

Cache structure per file::

    <path_hash>/
    ├── master.m3u8           # Multivariant playlist (built by Python)
    ├── video/
    │   ├── playlist.m3u8     # Video + default audio
    │   └── segment_0000.ts
    ├── audio_1/
    │   ├── playlist.m3u8     # Audio-only alternative track
    │   └── segment_0000.ts
    ├── sub_0/
    │   ├── playlist.m3u8     # WebVTT wrapper playlist
    │   └── sub.vtt
    └── tracks.json           # Cached probe result
"""

import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from src.modules.media.infrastructure.streaming._subprocess import SUBPROCESS_TEXT_KWARGS
from src.modules.media.infrastructure.streaming.media_probe_service import (
    MediaProbeResult,
    MediaProbeService,
)

_logger = logging.getLogger(__name__)

_SEGMENT_DURATION = 10  # seconds per segment
_POLL_INTERVAL = 0.5  # seconds between readiness checks
_POLL_TIMEOUT = 120  # max seconds to wait for first segment
_BROWSER_SAFE_CODECS = {"h264"}

# Number of segments ffmpeg must produce before ensure_playlist returns.
# When start_seconds > 0 we wait for more segments to give ffmpeg a head
# start over the player, since the player begins consuming from the same
# source position the encoder is writing to (no natural buffer build-up).
_MIN_SEGMENTS_FRESH = 1
_MIN_SEGMENTS_WITH_SEEK = 3

# Idle eviction defaults: kill ffmpeg after this many seconds with no
# segment requests. Trade-off: short timeout frees CPU faster after the
# user navigates away, but a paused user beyond this window will see the
# next segment fail and the player rebuffer when they resume.
_DEFAULT_IDLE_TIMEOUT = 30.0
_EVICTION_INTERVAL = 10.0

_VIDEO_DIR = "video"

# -- Playlist rewriting utilities (used by routes) ----------------------------

# Matches standalone relative references (non-comment lines)
_RELATIVE_REF_RE = re.compile(
    r"^(?!#)(?!https?://)(?!/)(.+)$",
    re.MULTILINE,
)
# Matches URI="..." with relative paths only (skip absolute/protocol URIs)
_URI_ATTR_RE = re.compile(r'URI="(?!https?://)(?!/)([^"]+)"')

_MEDIA_TYPES: dict[str, str] = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".vtt": "text/vtt",
}


def rewrite_m3u8(m3u8_text: str, base_url: str) -> str:
    """Prefix all relative references in an m3u8 with an absolute base URL."""
    result = _URI_ATTR_RE.sub(rf'URI="{base_url}/\1"', m3u8_text)
    return _RELATIVE_REF_RE.sub(rf"{base_url}/\1", result)


def media_type_for(filename: str) -> str:
    """Determine media type from file extension."""
    suffix = Path(filename).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


# -- Module helpers -----------------------------------------------------------


def _primary_audio_index(probe: MediaProbeResult) -> int:
    """Get the index of the primary audio track (first one, always index 0)."""
    return probe.audio_tracks[0].index if probe.audio_tracks else 0


class HlsService:
    """Generate and cache HLS segments for video files.

    Args:
        cache_dir: Directory to store generated HLS files.
        probe_service: Service to discover audio/subtitle tracks.
        idle_timeout: Seconds without segment requests before a running
            ffmpeg process is considered idle and killed. Defaults to 30s.
        enable_eviction: Whether to start the background eviction daemon.
            Defaults to False so unit tests don't leak threads — production
            code should pass True via the DI container.
    """

    def __init__(
        self,
        cache_dir: str = "./hls_cache",
        probe_service: MediaProbeService | None = None,
        idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
        enable_eviction: bool = False,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._probe = probe_service or MediaProbeService()
        self._processes: dict[str, list[subprocess.Popen[bytes]]] = {}
        # path_hash → monotonic timestamp of the most recent activity
        # (playlist request OR segment fetch). The eviction loop reads
        # this to decide which ffmpeg processes are idle.
        self._last_access: dict[str, float] = {}
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        if enable_eviction:
            self._start_eviction_thread()

    def _start_eviction_thread(self) -> None:
        """Spawn a daemon thread that periodically evicts idle processes."""
        thread = threading.Thread(
            target=self._eviction_loop,
            daemon=True,
            name="hls-eviction",
        )
        thread.start()

    def _eviction_loop(self) -> None:
        """Background loop: wake up periodically and evict idle ffmpegs."""
        while True:
            time.sleep(_EVICTION_INTERVAL)
            try:
                self.evict_idle()
            except Exception:
                _logger.exception("HLS eviction loop error")

    def _touch_access(self, path_hash: str) -> None:
        """Record that this cache bucket was just used."""
        with self._lock:
            self._last_access[path_hash] = time.monotonic()

    def evict_idle(self) -> list[str]:
        """Kill ffmpeg processes that haven't seen activity recently.

        Returns the list of evicted path_hashes (useful for tests).
        """
        now = time.monotonic()
        with self._lock:
            stale = [
                ph
                for ph, last in self._last_access.items()
                if now - last > self._idle_timeout and ph in self._processes
            ]
        evicted: list[str] = []
        for path_hash in stale:
            idle_for = now - self._last_access.get(path_hash, now)
            _logger.info("Evicting idle ffmpeg for %s (idle %.0fs)", path_hash, idle_for)
            self._kill_processes(path_hash)
            with self._lock:
                self._last_access.pop(path_hash, None)
            evicted.append(path_hash)
        return evicted

    # -- Public API ------------------------------------------------------------

    def get_path_hash(self, file_path: str, start_seconds: float = 0.0) -> str:
        """Get the hash key for a (file path, start offset) pair.

        Args:
            file_path: Absolute path to the source video file.
            start_seconds: Start offset in seconds for partial transcodes.

        Returns:
            Hex MD5 digest uniquely identifying the cache bucket. Different
            start offsets produce different hashes so partial transcodes do
            not collide with full transcodes on disk.
        """
        key = f"{file_path}:{start_seconds}" if start_seconds else file_path
        return hashlib.md5(key.encode()).hexdigest()

    def get_file_by_hash(self, path_hash: str, relative_path: str) -> Path | None:
        """Get any file from cache by hash + relative path.

        Includes path traversal protection via ``Path.is_relative_to``.
        Touches the access timestamp on hit so the eviction loop knows
        the cache is still being consumed by a player.
        """
        cache_root = (self._cache_dir / path_hash).resolve()
        target = (cache_root / relative_path).resolve()

        try:
            target.relative_to(cache_root)
        except ValueError:
            return None

        if not target.is_file():
            return None
        self._touch_access(path_hash)
        return target

    def is_complete(self, path_hash: str) -> bool:
        """Check if generation is fully complete."""
        video_playlist = self._cache_dir / path_hash / _VIDEO_DIR / "playlist.m3u8"
        if not video_playlist.is_file():
            flat = self._cache_dir / path_hash / "playlist.m3u8"
            if not flat.is_file():
                return False
            try:
                return "#EXT-X-ENDLIST" in flat.read_text(encoding="utf-8")
            except OSError:
                return False
        try:
            return "#EXT-X-ENDLIST" in video_playlist.read_text(encoding="utf-8")
        except OSError:
            return False

    def get_master_playlist(self, path_hash: str) -> str | None:
        """Get master playlist content, falling back to legacy flat playlist.

        Touches access time on hit so the player attaching to a still-warm
        cache resets the idle timer immediately.
        """
        for name in ("master.m3u8", "playlist.m3u8"):
            path = self._cache_dir / path_hash / name
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                self._touch_access(path_hash)
                return content
        return None

    def get_cached_tracks(self, path_hash: str) -> dict[str, Any] | None:
        """Get cached probe result from tracks.json."""
        tracks_file = self._cache_dir / path_hash / "tracks.json"
        if not tracks_file.is_file():
            return None
        try:
            data: dict[str, Any] = json.loads(tracks_file.read_text(encoding="utf-8"))
            return data
        except (OSError, json.JSONDecodeError):
            return None

    async def ensure_playlist(self, file_path: str, start_seconds: float = 0.0) -> str:
        """Start generation and wait until the first segments are ready.

        Args:
            file_path: Absolute path to the source video file.
            start_seconds: Start offset in seconds. FFmpeg seeks to this
                position before transcoding, so the first produced segment
                corresponds to (original time = start_seconds).

        Returns:
            The path hash for this (file, start) pair.

        Raises:
            RuntimeError: If FFmpeg is not available, fails, or times out.
            FileNotFoundError: If the source file does not exist.
        """
        path_hash = self.get_path_hash(file_path, start_seconds)
        # Touch immediately so the eviction loop never kills a process
        # that the user just asked for, even if no segments have been
        # served yet (e.g. while waiting for ffmpeg to start).
        self._touch_access(path_hash)

        if self.is_complete(path_hash):
            return path_hash

        if not shutil.which("ffmpeg"):
            msg = "FFmpeg is required for HLS streaming but was not found"
            raise RuntimeError(msg)

        source = Path(file_path)
        if not source.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)

        await asyncio.to_thread(self._start_generation, file_path, start_seconds)

        video_playlist = self._cache_dir / path_hash / _VIDEO_DIR / "playlist.m3u8"
        min_segments = _MIN_SEGMENTS_WITH_SEEK if start_seconds > 0 else _MIN_SEGMENTS_FRESH
        attempts = int(_POLL_TIMEOUT / _POLL_INTERVAL)
        for _ in range(attempts):
            if video_playlist.is_file():
                try:
                    content = video_playlist.read_text(encoding="utf-8")
                    # Count #EXTINF directives — these are only added by
                    # ffmpeg AFTER a segment is fully written and renamed,
                    # so anything counted here is safe to serve.
                    extinf_count = content.count("#EXTINF:")
                    if extinf_count >= min_segments:
                        return path_hash
                except OSError:
                    pass

            main_proc = self._get_main_process(path_hash)
            if main_proc and main_proc.poll() is not None:
                self._handle_generation_failure(path_hash, main_proc)

            await asyncio.sleep(_POLL_INTERVAL)

        msg = f"Timeout waiting for HLS segments ({_POLL_TIMEOUT}s)"
        raise RuntimeError(msg)

    def probe_tracks(self, file_path: str) -> MediaProbeResult:
        """Probe a file for tracks, using cache when available."""
        path_hash = self.get_path_hash(file_path)
        cached = self.get_cached_tracks(path_hash)
        if cached:
            return self._deserialize_probe(cached)
        return self._probe.probe(file_path)

    def clear_cache(
        self,
        file_path: str | None = None,
        start_seconds: float = 0.0,
    ) -> None:
        """Clear cached HLS segments.

        Args:
            file_path: Clear cache for specific file, or all if None.
            start_seconds: When ``file_path`` is given, targets the specific
                (file, start) bucket. Ignored when clearing the full cache.
        """
        if file_path:
            path_hash = self.get_path_hash(file_path, start_seconds)
            self._kill_processes(path_hash)
            shutil.rmtree(self._cache_dir / path_hash, ignore_errors=True)
        else:
            with self._lock:
                for path_hash in list(self._processes):
                    self._kill_processes(path_hash)
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    # -- Private: process management -------------------------------------------

    def _get_main_process(self, path_hash: str) -> subprocess.Popen[bytes] | None:
        """Get the main (video) FFmpeg process for a generation, if any."""
        with self._lock:
            procs = self._processes.get(path_hash, [])
        return procs[0] if procs else None

    def _kill_processes(self, path_hash: str) -> None:
        """Kill all running FFmpeg processes for a path hash."""
        with self._lock:
            for proc in self._processes.pop(path_hash, []):
                if proc.poll() is None:
                    proc.kill()
            self._last_access.pop(path_hash, None)

    def _handle_generation_failure(
        self,
        path_hash: str,
        proc: subprocess.Popen[bytes],
    ) -> None:
        """Log error, clean up cache, and raise for a failed FFmpeg process."""
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        _logger.error("FFmpeg exited with code %d: %s", proc.returncode, stderr)
        shutil.rmtree(self._cache_dir / path_hash, ignore_errors=True)
        msg = f"FFmpeg failed (exit {proc.returncode}): {stderr}"
        raise RuntimeError(msg)

    # -- Private: generation ---------------------------------------------------

    def _start_generation(self, file_path: str, start_seconds: float = 0.0) -> str:
        """Start all FFmpeg processes for multi-track HLS generation.

        Args:
            file_path: Absolute path to the source video file.
            start_seconds: Seek to this position before transcoding so the
                output starts at (original time = start_seconds).
        """
        source = self._validate_source(file_path)
        safe_path = str(source)
        path_hash = self.get_path_hash(file_path, start_seconds)

        if self.is_complete(path_hash):
            return path_hash

        # Probe outside the lock (potentially slow I/O)
        probe_result = self._probe.probe(safe_path)

        with self._lock:
            # Re-check after acquiring lock
            if self.is_complete(path_hash):
                return path_hash

            running = [p for p in self._processes.get(path_hash, []) if p.poll() is None]
            if running:
                return path_hash
            self._processes.pop(path_hash, None)

            # Clean stale cache
            output_dir = self._cache_dir / path_hash
            if output_dir.exists():
                _logger.info("Cleaning stale cache for %s", path_hash)
                shutil.rmtree(output_dir, ignore_errors=True)

            output_dir.mkdir(parents=True, exist_ok=True)
            self._save_probe_cache(output_dir, probe_result)

            procs: list[subprocess.Popen[bytes]] = []

            # 1. Main: video + default audio (always first in list)
            video_dir = output_dir / _VIDEO_DIR
            video_dir.mkdir()
            cmd = self._build_video_cmd(safe_path, video_dir, probe_result, start_seconds)
            _logger.info("Starting video HLS for %s (start=%ss)", safe_path, start_seconds)
            procs.append(self._spawn_ffmpeg(cmd))

            # 2. Additional audio tracks (audio-only HLS)
            primary_audio_idx = _primary_audio_index(probe_result)
            for track in probe_result.audio_tracks:
                if track.index == primary_audio_idx:
                    continue
                audio_dir = output_dir / f"audio_{track.index}"
                audio_dir.mkdir()
                cmd = self._build_audio_cmd(safe_path, audio_dir, track.index, start_seconds)
                _logger.info(
                    "Starting audio HLS for track %d (%s) of %s (start=%ss)",
                    track.index,
                    track.language.value,
                    safe_path,
                    start_seconds,
                )
                procs.append(self._spawn_ffmpeg(cmd))

            # 3. Extract subtitles to WebVTT (synchronous, fast)
            self._extract_subtitles(safe_path, output_dir, probe_result, start_seconds)

            # 4. Build master playlist
            self._build_master_playlist(output_dir, probe_result)

            self._processes[path_hash] = procs
            self._last_access[path_hash] = time.monotonic()

        return path_hash

    @staticmethod
    def _spawn_ffmpeg(cmd: list[str]) -> subprocess.Popen[bytes]:
        """Spawn an FFmpeg subprocess.

        All arguments are built internally from validated paths,
        not from user-controlled input.
        """
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    # -- Private: FFmpeg commands ----------------------------------------------

    @staticmethod
    def _probe_video_codec(file_path: str) -> str | None:
        """Detect video codec using ffprobe."""
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
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=10,
            )
            codec = result.stdout.strip().lower()
            return codec if codec else None
        except Exception:
            return None

    def _build_video_cmd(
        self,
        file_path: str,
        output_dir: Path,
        probe: MediaProbeResult,
        start_seconds: float = 0.0,
    ) -> list[str]:
        """Build FFmpeg command for video + default audio.

        When ``start_seconds > 0``, ``-ss`` is placed before ``-i`` so FFmpeg
        does a fast demuxer-level seek to the nearest keyframe before the
        requested position.
        """
        codec = self._probe_video_codec(file_path)
        needs_transcode = codec not in _BROWSER_SAFE_CODECS

        if needs_transcode:
            _logger.info("Source codec %s — transcoding to H.264", codec)
            video_args = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
        else:
            _logger.info("Source codec %s — copying", codec)
            video_args = ["-c:v", "copy"]

        primary_idx = _primary_audio_index(probe)
        audio_map = f"0:a:{primary_idx}"

        cmd = ["ffmpeg"]
        if start_seconds > 0:
            cmd.extend(["-ss", str(start_seconds)])
        cmd.extend(
            [
                "-i",
                file_path,
                "-map",
                "0:v:0",
                "-map",
                audio_map,
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
                # temp_file: write each segment to .ts.tmp and rename to .ts
                # only after it's fully written. Prevents the player from
                # racing the encoder and grabbing partial bytes.
                "-hls_flags",
                "temp_file",
                "-hls_segment_filename",
                str(output_dir / "segment_%04d.ts"),
                "-loglevel",
                "error",
                "-y",
                str(output_dir / "playlist.m3u8"),
            ]
        )
        return cmd

    @staticmethod
    def _build_audio_cmd(
        file_path: str,
        output_dir: Path,
        audio_index: int,
        start_seconds: float = 0.0,
    ) -> list[str]:
        """Build FFmpeg command for audio-only HLS track.

        When ``start_seconds > 0``, ``-ss`` is placed before ``-i`` so the
        audio track stays aligned with the video track (both start at the
        same source position).
        """
        cmd = ["ffmpeg"]
        if start_seconds > 0:
            cmd.extend(["-ss", str(start_seconds)])
        cmd.extend(
            [
                "-i",
                file_path,
                "-map",
                f"0:a:{audio_index}",
                "-vn",
                "-sn",
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
                "-hls_flags",
                "temp_file",
                "-hls_segment_filename",
                str(output_dir / "segment_%04d.ts"),
                "-loglevel",
                "error",
                "-y",
                str(output_dir / "playlist.m3u8"),
            ]
        )
        return cmd

    # -- Private: subtitle extraction ------------------------------------------

    @staticmethod
    def _extract_subtitles(
        file_path: str,
        output_dir: Path,
        probe: MediaProbeResult,
        start_seconds: float = 0.0,
    ) -> None:
        """Extract text-based subtitles to WebVTT files.

        When ``start_seconds > 0``, ``-ss`` is applied so subtitle timestamps
        are rebased to match the trimmed video output (both start at 0).
        """
        ss_args = ["-ss", str(start_seconds)] if start_seconds > 0 else []

        for track in probe.subtitle_tracks:
            if not track.is_text_based:
                _logger.info(
                    "Skipping image-based subtitle track %d (%s)",
                    track.index,
                    track.format,
                )
                continue

            sub_dir = output_dir / f"sub_{track.index}"
            sub_dir.mkdir(exist_ok=True)
            vtt_path = sub_dir / "sub.vtt"

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        *ss_args,
                        "-i",
                        file_path,
                        "-map",
                        f"0:s:{track.index}",
                        "-c:s",
                        "webvtt",
                        "-loglevel",
                        "error",
                        "-y",
                        str(vtt_path),
                    ],
                    **SUBPROCESS_TEXT_KWARGS,
                    check=False,
                    timeout=60,
                )
                if vtt_path.is_file():
                    _write_subtitle_playlist(sub_dir)
                    _logger.info("Extracted subtitle track %d to %s", track.index, vtt_path)
                else:
                    _logger.warning("Failed to extract subtitle track %d", track.index)
            except subprocess.TimeoutExpired:
                _logger.warning("Subtitle extraction timed out for track %d", track.index)

        for track in probe.external_subtitles:
            if not track.is_text_based or not track.file_path:
                continue

            sub_dir = output_dir / f"sub_{track.index}"
            sub_dir.mkdir(exist_ok=True)
            vtt_path = sub_dir / "sub.vtt"

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        *ss_args,
                        "-i",
                        track.file_path.value,
                        "-c:s",
                        "webvtt",
                        "-loglevel",
                        "error",
                        "-y",
                        str(vtt_path),
                    ],
                    **SUBPROCESS_TEXT_KWARGS,
                    check=False,
                    timeout=60,
                )
                if vtt_path.is_file():
                    _write_subtitle_playlist(sub_dir)
                    _logger.info(
                        "Converted external subtitle %s to %s",
                        track.file_path.value,
                        vtt_path,
                    )
            except subprocess.TimeoutExpired:
                _logger.warning("External subtitle conversion timed out for %s", track.file_path)

    # -- Private: master playlist ----------------------------------------------

    @staticmethod
    def _build_master_playlist(output_dir: Path, probe: MediaProbeResult) -> None:
        """Generate master.m3u8 with audio renditions and subtitle tracks."""
        lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

        has_alt_audio = len(probe.audio_tracks) > 1
        audio_group = 'AUDIO="audio"' if has_alt_audio else ""
        text_subs = [s for s in probe.all_subtitles if s.is_text_based]
        sub_group = 'SUBTITLES="subs"' if text_subs else ""

        primary_idx = _primary_audio_index(probe)
        if has_alt_audio:
            for track in probe.audio_tracks:
                is_primary = track.index == primary_idx
                name = track.title or f"{track.language.value.upper()} ({track.channel_layout})"
                if is_primary:
                    lines.append(
                        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                        f'NAME="{name}",LANGUAGE="{track.language.value}",'
                        f"DEFAULT=YES,AUTOSELECT=YES"
                    )
                else:
                    lines.append(
                        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                        f'NAME="{name}",LANGUAGE="{track.language.value}",'
                        f"DEFAULT=NO,AUTOSELECT=NO,"
                        f'URI="audio_{track.index}/playlist.m3u8"'
                    )

        for sub in text_subs:
            sub_name = sub.title or f"{sub.language.value.upper()}"
            is_forced = "YES" if sub.is_forced else "NO"
            lines.append(
                f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",'
                f'NAME="{sub_name}",LANGUAGE="{sub.language.value}",'
                f"DEFAULT=NO,AUTOSELECT=NO,FORCED={is_forced},"
                f'URI="sub_{sub.index}/playlist.m3u8"'
            )

        groups = ",".join(filter(None, [audio_group, sub_group]))
        stream_inf = "#EXT-X-STREAM-INF:BANDWIDTH=5000000"
        if groups:
            stream_inf += f",{groups}"
        lines.append(stream_inf)
        lines.append("video/playlist.m3u8")

        master_path = output_dir / "master.m3u8"
        master_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _logger.info("Master playlist written to %s", master_path)

    # -- Private: probe cache --------------------------------------------------

    @staticmethod
    def _save_probe_cache(output_dir: Path, probe: MediaProbeResult) -> None:
        """Save probe result as JSON for the tracks API."""
        data = {
            "audio_tracks": [
                {
                    "index": t.index,
                    "language": t.language.value,
                    "codec": t.codec,
                    "channels": t.channels,
                    "title": t.title,
                    "is_default": t.is_default,
                    "bitrate": t.bitrate,
                }
                for t in probe.audio_tracks
            ],
            "subtitle_tracks": [
                {
                    "index": t.index,
                    "language": t.language.value,
                    "format": t.format,
                    "title": t.title,
                    "is_default": t.is_default,
                    "is_forced": t.is_forced,
                    "is_external": t.is_external,
                    "is_image_based": t.is_image_based,
                }
                for t in probe.all_subtitles
            ],
        }
        (output_dir / "tracks.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _deserialize_probe(data: dict[str, Any]) -> MediaProbeResult:
        """Reconstruct MediaProbeResult from cached JSON."""
        from src.shared_kernel.value_objects.language_code import LanguageCode
        from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

        audio = [
            AudioTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                codec=t["codec"],
                channels=t["channels"],
                title=t.get("title"),
                is_default=t["is_default"],
                bitrate=t.get("bitrate"),
            )
            for t in data.get("audio_tracks", [])
        ]
        subs = [
            SubtitleTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                format=t["format"],
                title=t.get("title"),
                is_default=t.get("is_default", False),
                is_forced=t.get("is_forced", False),
                is_external=t.get("is_external", False),
            )
            for t in data.get("subtitle_tracks", [])
            if not t.get("is_external", False)
        ]
        ext = [
            SubtitleTrack(
                index=t["index"],
                language=LanguageCode(t["language"]),
                format=t["format"],
                title=t.get("title"),
                is_default=t.get("is_default", False),
                is_forced=t.get("is_forced", False),
                is_external=True,
                file_path=None,
            )
            for t in data.get("subtitle_tracks", [])
            if t.get("is_external", False)
        ]
        return MediaProbeResult(audio_tracks=audio, subtitle_tracks=subs, external_subtitles=ext)

    # -- Private: validation ---------------------------------------------------

    @staticmethod
    def _validate_source(file_path: str) -> Path:
        """Resolve and validate that file_path is an existing file."""
        resolved = Path(file_path).resolve()
        if not resolved.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)
        return resolved


def _write_subtitle_playlist(sub_dir: Path) -> None:
    """Write a simple HLS playlist wrapping a single VTT file."""
    playlist = sub_dir / "playlist.m3u8"
    playlist.write_text(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:99999\n"
        "#EXT-X-PLAYLIST-TYPE:VOD\n"
        "#EXTINF:99999,\n"
        "sub.vtt\n"
        "#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )


__all__ = ["HlsService", "media_type_for", "rewrite_m3u8"]
