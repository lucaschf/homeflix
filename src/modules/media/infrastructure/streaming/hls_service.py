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

Scrub-preview sprites used to live in ``thumbnails/`` here too. They
are now persisted next to each media file by ``ThumbnailBackfillJob``
and served by the id-based ``/scrub-preview/`` routes — this service
no longer touches them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.modules.media.application.ports.hls_playlist_port import (
    HlsCacheStats,
    HlsPlaylistPort,
)
from src.modules.media.application.ports.media_probe_port import ProbeResult
from src.modules.media.domain.services.track_naming import (
    TrackVersion,
    audio_version_labels,
    render_version_token,
    subtitle_version_labels,
)
from src.modules.media.infrastructure.streaming._subprocess import (
    HW_ACCEL_NVENC,
    HW_ACCEL_OFF,
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)
from src.modules.media.infrastructure.streaming.media_probe_service import MediaProbeService

if TYPE_CHECKING:
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings
    from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

_logger = logging.getLogger(__name__)

_SEGMENT_DURATION = 10  # seconds per segment
_POLL_INTERVAL = 0.5  # seconds between readiness checks
_POLL_TIMEOUT = 120  # max seconds to wait for first segment
_BROWSER_SAFE_CODECS = {"h264"}

# Number of segments ffmpeg must produce before ensure_playlist returns.
# The transcode always starts at t=0, so one segment is enough to give
# hls.js something to render; the rest stream in as they're written.
_MIN_SEGMENTS_FRESH = 1

# Idle eviction defaults: kill ffmpeg after this many seconds with no
# segment requests. Trade-off: short timeout frees CPU faster after the
# user navigates away, but a paused user beyond this window will see the
# next segment fail and the player rebuffer when they resume.
_DEFAULT_IDLE_TIMEOUT = 30.0
_EVICTION_INTERVAL = 10.0


_VIDEO_DIR = "video"

# Wall-clock cap for the one-time NVENC functional probe. Deliberately
# generous: the probe is the process's first CUDA call, so it absorbs the
# cold driver / context init, which was measured at ~20s on a cold but
# perfectly working GPU. Cutting this to a few seconds would time out
# that cold init and make AUTO mode fall back to software on a host that
# actually has a usable encoder — the exact false negative this feature
# exists to avoid. The cost (a longer first play once per process on a
# hung driver) fits inside the 120s first-segment budget.
_NVENC_PROBE_TIMEOUT = 30

# -- Module helpers -----------------------------------------------------------


def _primary_audio_index(probe: ProbeResult) -> int:
    """Get the index of the primary audio track (first one, always index 0)."""
    return probe.audio_tracks[0].index if probe.audio_tracks else 0


def _manifest_track_name(language: str, version: TrackVersion | None) -> str:
    """Compose a fallback ``NAME=`` for a manifest rendition.

    The manifest can't carry structured data and isn't localized, so we
    use the language code plus a short version token (e.g. "PT",
    "PT · Herbert Richers", "PT · 5.1"). Clients should prefer the
    structured ``/tracks`` payload and localize it themselves.
    """
    base = language.upper()
    token = render_version_token(version)
    return f"{base} · {token}" if token else base


def _audio_args_for(track: AudioTrack | None, start: int) -> list[str]:
    """Pick the ffmpeg audio args for one HLS track: copy or re-encode.

    Re-encoding every audio track to AAC stereo 48 kHz is wasted work
    when the source already *is* browser-playable AAC. We remux with
    ``-c:a copy`` only when the track is unambiguously safe to drop into
    MPEG-TS untouched:

    - **AAC-LC** — the one AAC profile MSE/hls.js decode everywhere;
      HE-AAC (SBR/PS) is excluded because browser support is spotty.
    - **stereo** — multichannel must be downmixed to 2.0 for the player.
    - **48 kHz** — matches the rate the re-encode path normalises to, so
      a copied stream is byte-for-byte what a transcode would have
      targeted.
    - **start == 0** — a non-zero resume offset re-encodes the video with
      ``-accurate_seek``; copying the audio there would land it at the
      nearest packet instead of the exact second and drift out of sync.

    Anything else (unknown profile/rate, non-AAC, surround, mid-stream
    seek) falls back to the safe AAC re-encode.
    """
    if (
        track is not None
        and start == 0
        and track.codec == "aac"
        and track.is_stereo
        and track.sample_rate == 48000
        and (track.profile or "").strip().upper() == "LC"
    ):
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-ac", "2", "-ar", "48000"]


class HlsService(HlsPlaylistPort):
    """Generate and cache HLS segments for video files.

    Args:
        cache_dir: Directory to store generated HLS files.
        runtime_settings: Snapshot facade for :class:`StreamingConfig`.
            ``ffmpeg_threads`` is read fresh per ffmpeg invocation;
            ``hls_cache_max_size_mb`` is read via the *sync* snapshot
            in the eviction daemon (so admin edits propagate on the
            next eviction tick, ~60s).
        probe_service: Service to discover audio/subtitle tracks.
        idle_timeout: Seconds without segment requests before a running
            ffmpeg process is considered idle and killed. Defaults to 30s.
        enable_eviction: Whether to start the background eviction daemon.
            Defaults to False so unit tests don't leak threads — production
            code should pass True via the DI container.
    """

    def __init__(
        self,
        runtime_settings: RuntimeSettings,
        cache_dir: str = "./hls_cache",
        probe_service: MediaProbeService | None = None,
        idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
        enable_eviction: bool = False,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._probe = probe_service or MediaProbeService()
        self._runtime_settings = runtime_settings
        self._processes: dict[str, list[subprocess.Popen[bytes]]] = {}
        # path_hash → monotonic timestamp of the most recent activity
        # (playlist request OR segment fetch). The eviction loop reads
        # this to decide which ffmpeg processes are idle.
        self._last_access: dict[str, float] = {}
        # path_hash → {subtitle_index: Event}. Set when a subtitle's
        # background extraction finishes (success or failure). The file
        # route uses these to block its response until the requested
        # subtitle is on disk, instead of returning a premature 404.
        self._subtitle_events: dict[str, dict[int, threading.Event]] = {}
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        # Memoised result of the one-time NVENC functional probe (None
        # until first transcode in AUTO mode forces the check).
        self._nvenc_probe: bool | None = None
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
        """Background loop: wake up periodically and evict idle ffmpegs + LRU cache."""
        while True:
            time.sleep(_EVICTION_INTERVAL)
            try:
                self.evict_idle()
                self.evict_lru()
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

    def evict_lru(self) -> list[str]:
        """Delete the least-recently-used cache buckets until total size is within the limit.

        Scans all subdirectories under ``cache_dir``, sums their sizes,
        and deletes the ones with the oldest ``_last_access`` timestamp
        (or oldest filesystem mtime if the hash isn't tracked in memory)
        until the total drops below ``max_cache_size_mb``.

        Active buckets (those with running ffmpeg processes) are skipped
        to avoid deleting segments a player is currently reading.

        Returns the list of evicted path_hashes (useful for tests).
        """
        max_cache_bytes = (
            self._runtime_settings.streaming_snapshot_sync().hls_cache_max_size_mb * 1024 * 1024
        )
        if max_cache_bytes <= 0:
            return []

        # Scan disk: collect (path_hash, size_bytes, last_access_time)
        buckets: list[tuple[str, int, float]] = []
        total_size = 0
        for entry in self._cache_dir.iterdir():
            if not entry.is_dir():
                continue
            path_hash = entry.name
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            total_size += size
            # Prefer in-memory access time; fall back to directory mtime
            with self._lock:
                access_time = self._last_access.get(path_hash, entry.stat().st_mtime)
            buckets.append((path_hash, size, access_time))

        if total_size <= max_cache_bytes:
            return []

        # Sort by access time ascending — oldest first
        buckets.sort(key=lambda b: b[2])

        evicted: list[str] = []
        for path_hash, size, _ in buckets:
            if total_size <= max_cache_bytes:
                break
            # Don't evict buckets with active ffmpeg processes
            with self._lock:
                if path_hash in self._processes:
                    continue
            bucket_path = self._cache_dir / path_hash
            _logger.info(
                "LRU evicting cache bucket %s (%.1f MB)",
                path_hash,
                size / (1024 * 1024),
            )
            shutil.rmtree(bucket_path, ignore_errors=True)
            with self._lock:
                self._last_access.pop(path_hash, None)
            total_size -= size
            evicted.append(path_hash)
        return evicted

    # -- Public API ------------------------------------------------------------

    def get_path_hash(self, file_path: str, start: int = 0) -> str:
        """Get the hash key for a source file at a given start offset.

        Args:
            file_path: Absolute path to the source video file.
            start: Source-time second the playback session starts from,
                honoured exactly so a forward seek (e.g. Skip Intro) can
                anchor a fresh encode at the target second instead of
                snapping onto a coarser bucket. Callers that want cache
                reuse across nearby positions (the resume flow) quantise
                ``start`` themselves before calling. ``0`` (the default)
                hashes the file path alone, keeping pre-existing cache
                directories valid after upgrade.

        Returns:
            Hex MD5 digest uniquely identifying the cache bucket. The
            seek-ahead and resume flows on cold cache rely on this
            being deterministic so the same offset always re-attaches
            to the same on-disk bucket.
        """
        key = file_path if start == 0 else f"{file_path}:{start}"
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
        """Check if every playlist in the bucket has been sealed with ENDLIST.

        A bucket is "complete" only when every nested ``playlist.m3u8``
        (video, alternate audios, subtitle wrappers) carries the
        ``#EXT-X-ENDLIST`` tag. The encode-watcher writes the tag on
        clean ffmpeg exit; subtitle wrappers are emitted with the tag
        baked in. Checking ALL playlists prevents the next session from
        skipping regeneration when the video encode finished cleanly
        but an alternate-audio encode was killed mid-flight.
        """
        bucket = self._cache_dir / path_hash
        if not bucket.is_dir():
            return False

        flat = bucket / "playlist.m3u8"
        nested_video_dir = bucket / _VIDEO_DIR
        if flat.is_file() and not nested_video_dir.is_dir():
            return _has_endlist(flat)

        playlists = list(bucket.glob("*/playlist.m3u8"))
        if not playlists:
            return False
        return all(_has_endlist(p) for p in playlists)

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

    def wait_for_subtitle(
        self,
        path_hash: str,
        sub_index: int,
        timeout: float,
    ) -> bool:
        """Block until a specific subtitle has finished extracting.

        Args:
            path_hash: Cache bucket hash returned by ``get_path_hash``.
            sub_index: Track index used to build ``sub_<index>/`` on disk.
            timeout: Max seconds to block. Should be longer than the
                worst-case ffmpeg subtitle extraction so the player gets
                the .vtt instead of a 404.

        Returns:
            ``True`` if the readiness event fired (extraction is done),
            or if the subtitle isn't being tracked at all (caller should
            fall through to a normal filesystem lookup). ``False`` only
            when the timeout elapsed before extraction completed.
        """
        with self._lock:
            event = self._subtitle_events.get(path_hash, {}).get(sub_index)
        if event is None:
            return True
        return event.wait(timeout)

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

    async def ensure_playlist(self, file_path: str, start: int = 0) -> str:
        """Start generation and wait until the first segments are ready.

        Args:
            file_path: Absolute path to the source video file.
            start: Source-time second to begin transcoding at, honoured
                exactly so a forward seek anchors a fresh encode on the
                target second. Callers wanting cache reuse across nearby
                positions quantise ``start`` before calling. ``0`` is the
                legacy behaviour (single bucket per file).

        Returns:
            The path hash for the bucket — unique per ``(file_path,
            start_bucket)`` pair.

        Raises:
            RuntimeError: If FFmpeg is not available, fails, or times out.
            FileNotFoundError: If the source file does not exist.
        """
        path_hash = self.get_path_hash(file_path, start)
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

        # Try the configured pipeline first; if a HW (NVENC/CUDA) attempt
        # fails — transient GPU contention, a 10-bit profile NVDEC can't
        # set up that moment — fall back to the proven libx264 path once
        # instead of surfacing a 500/404 to the player. Purely additive:
        # this only runs after the HW attempt already failed.
        hw_eligible = self._would_use_hw_transcode(file_path, start)
        try:
            await self._generate_and_wait(file_path, start, path_hash, force_software=False)
        except RuntimeError:
            if not hw_eligible:
                raise
            _logger.warning(
                "HW transcode failed for %s (start=%d) — retrying in software",
                file_path,
                start,
            )
            shutil.rmtree(self._cache_dir / path_hash, ignore_errors=True)
            self._kill_processes(path_hash)
            await self._generate_and_wait(file_path, start, path_hash, force_software=True)
        return path_hash

    def _would_use_hw_transcode(self, file_path: str, start: int) -> bool:
        """Whether the NVENC/CUDA pipeline would be chosen for this request.

        Drives the software-fallback decision: a HW-only failure (CUDA
        init, NVDEC capability, transient GPU contention) recovers on the
        libx264 path, whereas a software failure would just repeat.
        """
        if not self._use_nvenc():
            return False
        if start > 0:
            return True
        return self._probe_video_codec(file_path) not in _BROWSER_SAFE_CODECS

    async def _generate_and_wait(
        self,
        file_path: str,
        start: int,
        path_hash: str,
        *,
        force_software: bool,
    ) -> None:
        """Start generation and block until the first segments are ready.

        Raises:
            RuntimeError: if the ffmpeg process fails or no segments
                appear within the poll timeout.
        """
        await asyncio.to_thread(self._start_generation, file_path, start, force_software)

        video_playlist = self._cache_dir / path_hash / _VIDEO_DIR / "playlist.m3u8"
        attempts = int(_POLL_TIMEOUT / _POLL_INTERVAL)
        for _ in range(attempts):
            if video_playlist.is_file():
                try:
                    content = video_playlist.read_text(encoding="utf-8")
                    # Count #EXTINF directives — these are only added by
                    # ffmpeg AFTER a segment is fully written and renamed,
                    # so anything counted here is safe to serve.
                    extinf_count = content.count("#EXTINF:")
                    if extinf_count >= _MIN_SEGMENTS_FRESH:
                        return
                except OSError:
                    pass

            main_proc = self._get_main_process(path_hash)
            if main_proc and main_proc.poll() is not None:
                self._handle_generation_failure(path_hash, main_proc)

            await asyncio.sleep(_POLL_INTERVAL)

        msg = f"Timeout waiting for HLS segments ({_POLL_TIMEOUT}s)"
        raise RuntimeError(msg)

    def probe_tracks(self, file_path: str) -> ProbeResult:
        """Probe a file for tracks, using cache when available."""
        path_hash = self.get_path_hash(file_path)
        cached = self.get_cached_tracks(path_hash)
        if cached:
            return self._deserialize_probe(cached)
        return self._probe.probe(file_path)

    def clear_cache(self, file_path: str | None = None) -> None:
        """Clear cached HLS segments.

        Args:
            file_path: Clear cache for specific file, or all if ``None``.
        """
        if file_path:
            path_hash = self.get_path_hash(file_path)
            self._kill_processes(path_hash)
            shutil.rmtree(self._cache_dir / path_hash, ignore_errors=True)
        else:
            with self._lock:
                for path_hash in list(self._processes):
                    self._kill_processes(path_hash)
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._touch_last_cleared_marker()

    def get_cache_stats(self) -> HlsCacheStats:
        """Return total bytes on disk + the configured ceiling + last clear.

        The walk visits every file under the cache root and sums
        ``st_size``. Cheap enough for an admin survey — the same
        approach already runs inside ``evict_lru`` whenever the
        cache fills up — but not something to hammer; the admin
        page polls on demand only.
        """
        total = 0
        if self._cache_dir.exists():
            for entry in self._cache_dir.rglob("*"):
                if entry.is_file():
                    try:
                        total += entry.stat().st_size
                    except OSError:
                        # File raced with eviction / clear; skip.
                        continue
        max_bytes = (
            self._runtime_settings.streaming_snapshot_sync().hls_cache_max_size_mb * 1024 * 1024
        )
        return HlsCacheStats(
            size_bytes=total,
            max_bytes=max_bytes,
            last_cleared_at=self._read_last_cleared_marker(),
        )

    # -- Last-cleared marker --------------------------------------------------
    #
    # A small zero-byte file at ``<cache_dir>/.last_cleared`` whose
    # mtime captures when ``clear_cache`` was last called with
    # ``file_path=None``. Cheaper than wiring a new table and
    # survives restarts (in-memory state would not).

    def _last_cleared_marker_path(self) -> Path:
        return self._cache_dir / ".last_cleared"

    def _touch_last_cleared_marker(self) -> None:
        marker = self._last_cleared_marker_path()
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch(exist_ok=True)
        except OSError:
            # Don't let a marker write error mask a successful clear.
            pass

    def _read_last_cleared_marker(self) -> datetime | None:
        marker = self._last_cleared_marker_path()
        try:
            ts = marker.stat().st_mtime
        except OSError:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)

    # -- Private: process management -------------------------------------------

    def _get_main_process(self, path_hash: str) -> subprocess.Popen[bytes] | None:
        """Get the main (video) FFmpeg process for a generation, if any."""
        with self._lock:
            procs = self._processes.get(path_hash, [])
        return procs[0] if procs else None

    def _kill_processes(self, path_hash: str) -> None:
        """Kill all running FFmpeg processes for a path hash.

        Also releases any waiters parked on subtitle readiness events for
        this bucket so they don't block their full timeout after we've
        already torn down the cache.
        """
        with self._lock:
            for proc in self._processes.pop(path_hash, []):
                if proc.poll() is None:
                    proc.kill()
            self._last_access.pop(path_hash, None)
            events = self._subtitle_events.pop(path_hash, {})
        for event in events.values():
            event.set()

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

    def _start_generation(
        self, file_path: str, start: int = 0, force_software: bool = False
    ) -> str:
        """Start all FFmpeg processes for multi-track HLS generation.

        Transcodes from the exact ``start`` second into a bucket keyed
        by ``(file_path, start)``. Each ffmpeg invocation gets ``-ss N``
        as an input seek so the encode skips fast to the nearest
        preceding keyframe before producing segments. ENDLIST sealing
        happens via the watcher spawned in ``_spawn_ffmpeg``.

        Args:
            file_path: Absolute path to the source video file.
            start: Source-time second to begin the encode at.
            force_software: Skip the NVENC pipeline and encode with
                libx264 — the fallback used after a HW attempt fails.
        """
        source = self._validate_source(file_path)
        safe_path = str(source)
        path_hash = self.get_path_hash(file_path, start)
        # The encode is anchored at the exact requested second so a
        # forward seek lands on the first segment of a fresh manifest
        # (no out-of-range seek on the live/event playlist). Cache reuse
        # for nearby resume positions is the caller's responsibility —
        # the resume flow quantises ``start`` before it gets here.
        bucket_start = start

        if self.is_complete(path_hash):
            return path_hash

        # Probe outside the lock (potentially slow I/O)
        probe_result = self._probe.probe(safe_path)

        # Snapshot ffmpeg_threads once per generation start so every
        # command spawned for this path sees the same cap, even if
        # an admin edit happens between spawns.
        ffmpeg_threads = self._runtime_settings.streaming_snapshot_sync().ffmpeg_threads

        # Pick the subtitles we'll actually try to convert. Image-based
        # tracks (PGS, VOBSUB) and externals without a resolved file path
        # are filtered out so we don't create dangling readiness events
        # the file route would block on indefinitely.
        text_subs: list[SubtitleTrack] = [
            s
            for s in probe_result.all_subtitles
            if s.is_text_based and (not s.is_external or s.file_path is not None)
        ]

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
            cmd = with_ffmpeg_threads(
                self._build_video_cmd(
                    safe_path, video_dir, probe_result, bucket_start, force_software
                ),
                ffmpeg_threads,
            )
            _logger.info("Starting video HLS for %s (offset=%ds)", safe_path, bucket_start)
            procs.append(
                self._spawn_ffmpeg(cmd, playlist_path=video_dir / "playlist.m3u8"),
            )

            # 2. Additional audio tracks (audio-only HLS)
            primary_audio_idx = _primary_audio_index(probe_result)
            for track in probe_result.audio_tracks:
                if track.index == primary_audio_idx:
                    continue
                audio_dir = output_dir / f"audio_{track.index}"
                audio_dir.mkdir()
                cmd = with_ffmpeg_threads(
                    self._build_audio_cmd(safe_path, audio_dir, track, bucket_start),
                    ffmpeg_threads,
                )
                _logger.info(
                    "Starting audio HLS for track %d (%s) of %s (offset=%ds)",
                    track.index,
                    track.language.value,
                    safe_path,
                    bucket_start,
                )
                procs.append(
                    self._spawn_ffmpeg(cmd, playlist_path=audio_dir / "playlist.m3u8"),
                )

            # 3. Build master playlist now — it references sub_N/playlist.m3u8
            # paths that get filled in by the background subtitle extraction
            # below. The player only fetches those URIs when the user enables
            # a subtitle (all entries are emitted as DEFAULT=NO,AUTOSELECT=NO),
            # so racing them against playback start is safe.
            self._build_master_playlist(output_dir, probe_result)

            # 4. Pre-create per-subtitle readiness events. They MUST be
            # registered before _start_generation returns so the file
            # route can find them the instant the player picks a track.
            if text_subs:
                self._subtitle_events[path_hash] = {
                    sub.index: threading.Event() for sub in text_subs
                }

            self._processes[path_hash] = procs
            self._last_access[path_hash] = time.monotonic()

        # 5. Extract each subtitle in its own background thread. Running
        # them in parallel (instead of one big serial thread) means a
        # user-selected subtitle only waits for its own ffmpeg, not for
        # every other track that happens to be earlier in the list.
        for sub in text_subs:
            threading.Thread(
                target=self._extract_one_subtitle,
                args=(safe_path, output_dir, sub, path_hash, bucket_start),
                daemon=True,
                name=f"hls-sub-{path_hash[:8]}-{sub.index}",
            ).start()

        return path_hash

    def _spawn_ffmpeg(
        self,
        cmd: list[str],
        playlist_path: Path | None = None,
    ) -> subprocess.Popen[bytes]:
        """Spawn an FFmpeg subprocess.

        All arguments are built internally from validated paths,
        not from user-controlled input.

        When ``playlist_path`` is provided, a daemon thread waits for
        the process and seals the playlist with ``#EXT-X-ENDLIST`` on
        clean exit (returncode 0). This is what makes ``is_complete``
        flip to True after a successful full encode, so the next
        session reuses the cache instead of respawning ffmpeg.
        """
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if playlist_path is not None:
            threading.Thread(
                target=self._watch_for_endlist,
                args=(proc, playlist_path),
                daemon=True,
                name=f"hls-endlist-{playlist_path.parent.name}",
            ).start()
        return proc

    @staticmethod
    def _watch_for_endlist(
        proc: subprocess.Popen[bytes],
        playlist_path: Path,
    ) -> None:
        """Wait for an ffmpeg encode to finish; seal the playlist on success.

        Skips the seal on any non-zero exit — eviction killing the
        process (negative returncode from SIGKILL) or ffmpeg failing
        partway both fall through here and leave the playlist as a
        growing event stream, so the next session correctly
        regenerates instead of treating a half-encoded cache as final.
        """
        try:
            returncode = proc.wait()
        except Exception:
            _logger.exception("ffmpeg watcher for %s failed", playlist_path)
            return
        if returncode != 0:
            return
        try:
            _append_endlist_atomic(playlist_path)
            _logger.info("Sealed HLS playlist with ENDLIST: %s", playlist_path)
        except OSError:
            _logger.exception("Failed to append ENDLIST to %s", playlist_path)

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

    @staticmethod
    def _detect_nvenc() -> bool:
        """Functionally probe whether ``h264_nvenc`` can actually encode.

        The encoder being *listed* by ffmpeg is not enough — a host can
        ship an ffmpeg with NVENC compiled in while lacking the GPU,
        driver, or a free encode session. We run a sub-second throwaway
        encode of a synthetic source through CUDA so AUTO mode only
        commits to NVENC when the full decode→encode path works.

        Returns ``True`` only on a clean (exit 0) probe encode.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=256x256:r=10",
                    "-t",
                    "0.2",
                    "-c:v",
                    "h264_nvenc",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=_NVENC_PROBE_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def _nvenc_available(self) -> bool:
        """Return the memoised NVENC functional-probe result.

        Probed at most once per service instance — the first transcode
        in AUTO mode pays the ~1s cold-start CUDA init, every later call
        reads the cached boolean.
        """
        if self._nvenc_probe is None:
            self._nvenc_probe = self._detect_nvenc()
            _logger.info("NVENC functional probe result: %s", self._nvenc_probe)
        return self._nvenc_probe

    def _use_nvenc(self) -> bool:
        """Decide whether this transcode should use NVENC.

        Honours the persisted ``hw_accel`` knob: ``off`` forces
        software, ``nvenc`` forces hardware (a broken encoder then
        surfaces as a transcode failure rather than silently falling
        back), and ``auto`` defers to the cached functional probe.
        """
        mode = self._runtime_settings.streaming_snapshot_sync().hw_accel
        if mode == HW_ACCEL_OFF:
            return False
        if mode == HW_ACCEL_NVENC:
            return True
        return self._nvenc_available()

    def _build_video_cmd(
        self,
        file_path: str,
        output_dir: Path,
        probe: ProbeResult,
        start: int = 0,
        force_software: bool = False,
    ) -> list[str]:
        """Build FFmpeg command for video + default audio.

        Transcodes (or remuxes, for already-H.264 sources) from the
        ``start`` second of the file. ``-ss`` is placed BEFORE ``-i``
        so ffmpeg does an input seek — fast and keyframe-accurate —
        and the resulting segments carry timestamps starting near zero
        in bucket-local time. Bucket-local timestamps are why the
        frontend computes ``video.currentTime = saved - bucket_start``
        instead of ``video.currentTime = saved`` (which would only
        work with ``-copyts`` / source-time preserved, a path the
        prior attempts at this refactor never landed reliably).

        When ``start > 0`` we also emit ``-accurate_seek`` and
        ``-avoid_negative_ts make_zero``. The first forces ffmpeg to
        decode-and-drop frames between the preceding keyframe and the
        exact requested second; without it, video opens at the
        keyframe while audio opens at ``start`` and the two streams
        play out of sync by that gap. The second clamps the minimum
        PTS to zero across streams so any residual offset surfaces as
        a tiny silence prefix instead of an audio-leads-video drift.

        The H.264 ``-c:v copy`` fast path is bypassed for non-zero
        ``start`` because copying skips the decode pass that
        ``-accurate_seek`` relies on to drop pre-target frames — the
        copied video would land at the preceding keyframe while the
        re-encoded audio lands at the exact ``start``, recreating the
        same 1-3s gap the seek flag was meant to close.

        When a transcode is required and ``hw_accel`` resolves to NVENC,
        the whole pipeline runs on the GPU: ``-hwaccel cuda`` decodes
        with NVDEC, ``scale_cuda=format=nv12`` does the 10-bit→8-bit
        conversion in VRAM, and ``h264_nvenc`` encodes — keeping the CPU
        almost idle and staying well above real-time on 4K HEVC. The
        software ``libx264`` path is the fallback.
        """
        codec = self._probe_video_codec(file_path)
        needs_transcode = codec not in _BROWSER_SAFE_CODECS or start > 0

        hwaccel_input_args: list[str] = []
        vf_args: list[str] = []

        if needs_transcode and self._use_nvenc() and not force_software:
            _logger.info("Source codec %s — transcoding via NVENC (start=%d)", codec, start)
            # Full-GPU pipeline: NVDEC decode → scale_cuda (10→8 bit in
            # VRAM) → NVENC encode. ``spatial_aq`` redistributes bits to
            # flat regions, which is what keeps sky/fog gradients from
            # banding. ``-cq 19`` is constant-quality VBR (``-b:v 0``).
            hwaccel_input_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
            vf_args = ["-vf", "scale_cuda=format=nv12"]
            video_args = [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p5",
                "-tune",
                "hq",
                "-rc",
                "vbr",
                "-cq",
                "19",
                "-b:v",
                "0",
                "-spatial_aq",
                "1",
            ]
        elif needs_transcode:
            _logger.info("Source codec %s — transcoding via libx264 (start=%d)", codec, start)
            # ``superfast`` (not ``ultrafast``) is the floor here: ultrafast
            # disables CABAC and adaptive quantization, which is exactly what
            # collapses smooth gradients (sky, fog) into visible macroblocks
            # on HEVC/10-bit sources re-encoded to H.264. superfast turns both
            # back on for a moderate CPU cost while staying real-time on 4K.
            # ``-pix_fmt yuv420p`` forces a clean 8-bit output so 10-bit
            # sources (yuv420p10le) downconvert through swscale's dithering
            # instead of producing an unplayable High 10 stream.
            video_args = [
                "-c:v",
                "libx264",
                "-preset",
                "superfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            _logger.info("Source codec %s — copying", codec)
            # H.264 inside MP4/MKV is AVCC (length-prefixed NALs) with
            # SPS/PPS only in container extradata. The HLS muxer does not
            # reliably auto-insert the Annex-B conversion the bare mpegts
            # muxer applies, so sources that don't repeat parameter sets
            # in-band lose them in the .ts segments — the browser decodes
            # zero frames (black video, audio fine). h264_mp4toannexb
            # converts to Annex-B and writes SPS/PPS in-band; it is a
            # no-op for streams already in Annex-B form.
            video_args = ["-c:v", "copy", "-bsf:v", "h264_mp4toannexb"]

        primary_idx = _primary_audio_index(probe)
        audio_map = f"0:a:{primary_idx}"
        primary_track = probe.audio_tracks[0] if probe.audio_tracks else None
        audio_args = _audio_args_for(primary_track, start)

        seek_args = ["-ss", str(start), "-accurate_seek"] if start > 0 else []
        ts_normalize_args = ["-avoid_negative_ts", "make_zero"] if start > 0 else []

        return [
            "ffmpeg",
            *hwaccel_input_args,
            *seek_args,
            "-i",
            file_path,
            "-map",
            "0:v:0",
            "-map",
            audio_map,
            "-sn",
            *vf_args,
            *video_args,
            *audio_args,
            *ts_normalize_args,
            # Zero the MPEG-TS muxer's ~1.4s initial offset so the first
            # segment PTS starts at ~0, keeping the video / audio / subtitle
            # timelines aligned (the WebVTT X-TIMESTAMP-MAP anchors to MPEGTS:0).
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
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

    @staticmethod
    def _build_audio_cmd(
        file_path: str,
        output_dir: Path,
        track: AudioTrack,
        start: int = 0,
    ) -> list[str]:
        """Build FFmpeg command for audio-only HLS track.

        ``-ss`` placed before ``-i`` when ``start > 0`` — same input-seek
        rationale as ``_build_video_cmd``. The alternate-audio playlist
        is consumed independently by the player; even though there is
        no video stream here, we still match the video pipeline's
        ``-accurate_seek`` / ``-avoid_negative_ts make_zero`` so a
        switch from primary to alternate audio at a non-zero bucket
        lands on the same source-time second.

        Like the primary audio in ``_build_video_cmd``, a browser-ready
        AAC-LC stereo 48 kHz source is remuxed with ``-c:a copy`` instead
        of re-encoded; see :func:`_audio_args_for`.
        """
        seek_args = ["-ss", str(start), "-accurate_seek"] if start > 0 else []
        ts_normalize_args = ["-avoid_negative_ts", "make_zero"] if start > 0 else []
        return [
            "ffmpeg",
            *seek_args,
            "-i",
            file_path,
            "-map",
            f"0:a:{track.index}",
            "-vn",
            "-sn",
            *_audio_args_for(track, start),
            *ts_normalize_args,
            # Zero the MPEG-TS muxer's ~1.4s initial offset so the first
            # segment PTS starts at ~0, keeping the video / audio / subtitle
            # timelines aligned (the WebVTT X-TIMESTAMP-MAP anchors to MPEGTS:0).
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
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

    # -- Private: subtitle extraction ------------------------------------------

    def _extract_one_subtitle(
        self,
        file_path: str,
        output_dir: Path,
        track: SubtitleTrack,
        path_hash: str,
        start: int = 0,
    ) -> None:
        """Extract a single text-based subtitle to WebVTT.

        Runs ffmpeg synchronously and signals the readiness Event for
        this track in ``self._subtitle_events`` from a ``finally``
        block, so any route handler waiting on it always unblocks (even
        on ffmpeg failure or timeout) and gets a chance to respond —
        typically with a 404 if extraction never produced a file.

        Subtitle cues are emitted in the same timeline as the HLS
        stream that wraps them. ffmpeg is invoked WITHOUT ``-ss`` so
        the full subtitle stream is written in source-time — that
        cmd-line worked uniformly across MKV/MP4/SRT demuxers; using
        ``-ss N`` instead produced container-dependent results
        (cues either late by ``N`` seconds or compressed to bucket
        start by ``-avoid_negative_ts``). After the extraction
        succeeds the post-processor ``_shift_webvtt_to_bucket_local``
        subtracts ``start`` from every cue, clamping negatives to
        zero, so cue at source-K lands at bucket-local ``K - start``.
        """
        try:
            sub_dir = output_dir / f"sub_{track.index}"
            sub_dir.mkdir(exist_ok=True)
            vtt_path = sub_dir / "sub.vtt"

            cmd_and_label = self._build_subtitle_extract_cmd(track, file_path, vtt_path)
            if cmd_and_label is None:
                return
            cmd, log_label = cmd_and_label
            if not self._run_subtitle_ffmpeg(cmd, log_label):
                return

            if vtt_path.is_file():
                if start > 0:
                    _shift_webvtt_to_bucket_local(vtt_path, start)
                _ensure_vtt_timestamp_map(vtt_path)
                _write_subtitle_playlist(sub_dir)
                _logger.info("Extracted %s to %s (start=%d)", log_label, vtt_path, start)
            else:
                _logger.warning("Failed to extract %s", log_label)
        finally:
            with self._lock:
                event = self._subtitle_events.get(path_hash, {}).get(track.index)
            if event is not None:
                event.set()

    def _build_subtitle_extract_cmd(
        self,
        track: SubtitleTrack,
        file_path: str,
        vtt_path: Path,
    ) -> tuple[list[str], str] | None:
        """Build the ffmpeg argv + log label for a single subtitle track.

        Returns ``None`` when the track is unusable (external sidecar
        with no resolved file path). The cmd is wrapped through
        ``with_ffmpeg_threads`` so the global cap applies uniformly.
        """
        ffmpeg_threads = self._runtime_settings.streaming_snapshot_sync().ffmpeg_threads
        if track.is_external:
            if track.file_path is None:
                return None
            cmd = with_ffmpeg_threads(
                [
                    "ffmpeg",
                    "-i",
                    track.file_path.value,
                    "-c:s",
                    "webvtt",
                    "-loglevel",
                    "error",
                    "-y",
                    str(vtt_path),
                ],
                ffmpeg_threads,
            )
            return cmd, f"external subtitle {track.file_path.value}"
        cmd = with_ffmpeg_threads(
            [
                "ffmpeg",
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
            ffmpeg_threads,
        )
        return cmd, f"subtitle track {track.index}"

    @staticmethod
    def _run_subtitle_ffmpeg(cmd: list[str], log_label: str) -> bool:
        """Run a subtitle ffmpeg cmd, returning True iff it didn't time out."""
        try:
            subprocess.run(
                cmd,
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("Extraction timed out for %s", log_label)
            return False
        return True

    # -- Private: master playlist ----------------------------------------------

    @staticmethod
    def _build_master_playlist(output_dir: Path, probe: ProbeResult) -> None:
        """Generate master.m3u8 with audio renditions and subtitle tracks."""
        lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

        has_alt_audio = len(probe.audio_tracks) > 1
        audio_group = 'AUDIO="audio"' if has_alt_audio else ""
        text_subs = [s for s in probe.all_subtitles if s.is_text_based]
        sub_group = 'SUBTITLES="subs"' if text_subs else ""

        audio_versions = audio_version_labels(probe.audio_tracks)
        sub_versions = subtitle_version_labels(text_subs)

        primary_idx = _primary_audio_index(probe)
        if has_alt_audio:
            for track in probe.audio_tracks:
                is_primary = track.index == primary_idx
                name = _manifest_track_name(track.language.value, audio_versions.get(track.index))
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
            sub_name = _manifest_track_name(sub.language.value, sub_versions.get(sub.index))
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
    def _save_probe_cache(output_dir: Path, probe: ProbeResult) -> None:
        """Save probe result as JSON for the tracks API."""
        data = {
            "resolution": probe.resolution,
            "audio_tracks": [
                {
                    "index": t.index,
                    "language": t.language.value,
                    "codec": t.codec,
                    "channels": t.channels,
                    "title": t.title,
                    "is_default": t.is_default,
                    "bitrate": t.bitrate,
                    "sample_rate": t.sample_rate,
                    "profile": t.profile,
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
    def _deserialize_probe(data: dict[str, Any]) -> ProbeResult:
        """Reconstruct ProbeResult from cached JSON."""
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
                sample_rate=t.get("sample_rate"),
                profile=t.get("profile"),
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
        return ProbeResult(
            audio_tracks=audio,
            subtitle_tracks=subs,
            external_subtitles=ext,
            resolution=data.get("resolution"),
        )

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


def _has_endlist(playlist_path: Path) -> bool:
    """Return ``True`` iff the playlist file exists and contains ``#EXT-X-ENDLIST``."""
    try:
        return "#EXT-X-ENDLIST" in playlist_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _append_endlist_atomic(playlist_path: Path) -> None:
    """Append ``#EXT-X-ENDLIST`` to a playlist via temp-file + atomic rename.

    Idempotent — returns early if the tag is already present. The
    rename is atomic on POSIX and on Windows (``Path.replace``), so a
    concurrent playlist GET sees either the pre-ENDLIST content or the
    sealed one, never a torn write.
    """
    if not playlist_path.is_file():
        return
    content = playlist_path.read_text(encoding="utf-8")
    if "#EXT-X-ENDLIST" in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    content += "#EXT-X-ENDLIST\n"
    tmp_path = playlist_path.with_name(playlist_path.name + ".endlist.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(playlist_path)


# Matches WebVTT cue timestamps in either ``mm:ss.fff`` (under one hour)
# or ``hh:mm:ss.fff`` shape, so the post-processor can shift cues
# regardless of which form ffmpeg picked when writing the file.
_VTT_TIMESTAMP_RE = re.compile(r"(?:(?P<h>\d+):)?(?P<m>\d{2}):(?P<s>\d{2})\.(?P<ms>\d{3})")


def _shift_one_timestamp(match: re.Match[str], shift_seconds: int) -> str:
    """Return the WebVTT timestamp in ``match`` shifted back by ``shift_seconds``.

    Negatives clamp to zero so a cue that straddled the bucket
    boundary collapses to ``00:00:00.000`` (start == end → the player
    skips it) instead of producing an invalid VTT line.
    """
    h = int(match.group("h") or 0)
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = int(match.group("ms"))
    total_ms = ((h * 60 + m) * 60 + s) * 1000 + ms - shift_seconds * 1000
    if total_ms < 0:
        total_ms = 0
    new_h, rem = divmod(total_ms, 3_600_000)
    new_m, rem = divmod(rem, 60_000)
    new_s, new_ms = divmod(rem, 1_000)
    return f"{new_h:02d}:{new_m:02d}:{new_s:02d}.{new_ms:03d}"


# Windows refuses os.replace onto a file another handle has open (a
# player fetching the .vtt, or an AV/indexer scanning a fresh write),
# raising PermissionError. The lock is transient, so retry briefly.
_VTT_REPLACE_ATTEMPTS = 5
_VTT_REPLACE_BACKOFF = 0.1  # seconds, scaled by attempt number


def _atomic_write_text(dest: Path, content: str) -> None:
    """Atomically write ``content`` onto ``dest``, retrying a locked replace.

    The unique temp name keeps two concurrent writers from clobbering
    each other's temp (``WinError 2``); the retry rides out a momentary
    open handle on the destination (``WinError 5``). Best-effort — gives
    up and cleans the temp after a few attempts.
    """
    tmp_path = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
    except OSError:
        _logger.exception("Failed to write temp for %s", dest)
        return
    for attempt in range(_VTT_REPLACE_ATTEMPTS):
        try:
            tmp_path.replace(dest)
            return
        except PermissionError:
            if attempt == _VTT_REPLACE_ATTEMPTS - 1:
                _logger.warning(
                    "Could not replace %s after %d tries (file locked)",
                    dest,
                    _VTT_REPLACE_ATTEMPTS,
                )
            else:
                time.sleep(_VTT_REPLACE_BACKOFF * (attempt + 1))
        except OSError:
            _logger.exception("Failed to replace %s", dest)
            break
    tmp_path.unlink(missing_ok=True)


def _shift_webvtt_to_bucket_local(vtt_path: Path, shift_seconds: int) -> None:
    """Subtract ``shift_seconds`` from every cue timestamp in the VTT.

    The extracted subtitle carries source-time cue timestamps; on a
    non-zero bucket start the player runs a bucket-local clock and
    every cue would otherwise fire ``shift_seconds`` seconds after
    the spoken line. Shift everything once on disk so hls.js can map
    cues to the active manifest's timeline without further help.
    """
    if shift_seconds <= 0:
        return
    if not vtt_path.is_file():
        return
    try:
        content = vtt_path.read_text(encoding="utf-8")
    except OSError:
        _logger.exception("Failed to read VTT for shifting: %s", vtt_path)
        return

    def _replace(m: re.Match[str]) -> str:
        return _shift_one_timestamp(m, shift_seconds)

    new_content = _VTT_TIMESTAMP_RE.sub(_replace, content)
    _atomic_write_text(vtt_path, new_content)


_VTT_TIMESTAMP_MAP = "X-TIMESTAMP-MAP=MPEGTS:0,LOCAL:00:00:00.000"


def _ensure_vtt_timestamp_map(vtt_path: Path) -> None:
    """Insert the HLS ``X-TIMESTAMP-MAP`` header into a standalone WebVTT.

    The video segments start at MPEG-TS PTS 0 (muxdelay/muxpreload
    zeroed), so cues anchored to ``LOCAL`` 0 line up with the video
    clock. Without this header hls.js falls back to the muxer's old
    ~1.4 s start offset and renders subtitles a second or two early.
    Idempotent and best-effort — runs after any bucket-local shift so it
    never rewrites the map's own ``00:00:00.000``.
    """
    if not vtt_path.is_file():
        return
    try:
        content = vtt_path.read_text(encoding="utf-8")
    except OSError:
        _logger.exception("Failed to read VTT for timestamp map: %s", vtt_path)
        return
    if "X-TIMESTAMP-MAP" in content:
        return
    # ffmpeg writes "WEBVTT\n\n<cues>"; the map must sit on the line
    # right after the WEBVTT signature, before the blank line + cues.
    head, _, rest = content.partition("\n")
    if "WEBVTT" not in head:
        return
    new_content = f"{head}\n{_VTT_TIMESTAMP_MAP}\n{rest}"
    _atomic_write_text(vtt_path, new_content)


__all__ = ["HlsService"]
