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

``HlsService`` is a thin orchestrator: process handles, subtitle
readiness, and the on-disk cache are owned by three collaborators
(:class:`FfmpegProcessManager`, :class:`SubtitlePipeline`,
:class:`HlsCacheStore`) that all share ONE reentrant lock. The two
operations that mutate more than one collaborator atomically —
``_kill_processes`` and ``_start_generation`` — hold that lock while
driving the collaborators, which is what the reentrancy buys.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.modules.media.application.ports.hls_playlist_port import (
    HlsCacheStats,
    HlsPlaylistPort,
)
from src.modules.media.infrastructure.streaming._hls_common import (
    _VIDEO_DIR,
    BROWSER_SAFE_CODECS,
    primary_audio_index,
)
from src.modules.media.infrastructure.streaming._subprocess import (
    with_ffmpeg_threads,
)
from src.modules.media.infrastructure.streaming.ffmpeg_process_manager import (
    FfmpegProcessManager,
)
from src.modules.media.infrastructure.streaming.hardware_acceleration_probe import (
    HardwareAccelerationProbe,
)
from src.modules.media.infrastructure.streaming.hls_cache_store import HlsCacheStore
from src.modules.media.infrastructure.streaming.master_playlist_writer import MasterPlaylistWriter
from src.modules.media.infrastructure.streaming.media_probe_service import MediaProbeService
from src.modules.media.infrastructure.streaming.probe_cache_store import ProbeCacheStore
from src.modules.media.infrastructure.streaming.subtitle_ocr_surfacing import (
    attach_ocr_subtitles,
)
from src.modules.media.infrastructure.streaming.subtitle_pipeline import SubtitlePipeline
from src.modules.media.infrastructure.streaming.transcode_command_builder import (
    TranscodeCommandBuilder,
)

if TYPE_CHECKING:
    from src.modules.media.application.ports.media_probe_port import ProbeResult
    from src.modules.media.application.ports.runtime_config_ports import HlsRuntimeConfigPort
    from src.shared_kernel.value_objects.tracks import SubtitleTrack

_logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.5  # seconds between readiness checks
_POLL_TIMEOUT = 120  # max seconds to wait for first segment

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
        runtime_settings: HlsRuntimeConfigPort,
        cache_dir: str = "./hls_cache",
        probe_service: MediaProbeService | None = None,
        idle_timeout: float = _DEFAULT_IDLE_TIMEOUT,
        enable_eviction: bool = False,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._probe = probe_service or MediaProbeService()
        self._runtime_settings = runtime_settings
        # Extracted collaborators (pure — no locks/threads/process state).
        self._hw_probe = HardwareAccelerationProbe(runtime_settings)
        self._cmd_builder = TranscodeCommandBuilder(self._hw_probe)
        self._probe_cache = ProbeCacheStore(self._cache_dir)
        self._master_writer = MasterPlaylistWriter()
        # ONE reentrant lock shared across every collaborator that guards
        # process/subtitle state. Reentrancy lets the orchestrator hold it
        # while a collaborator method re-acquires it — the invariant that
        # keeps _kill_processes and _start_generation single atomic
        # critical sections after the split.
        self._lock = threading.RLock()
        self._proc_mgr = FfmpegProcessManager(self._lock, idle_timeout)
        self._subtitles = SubtitlePipeline(self._lock, self._cache_dir, runtime_settings)
        self._cache_store = HlsCacheStore(self._cache_dir, runtime_settings, self._proc_mgr)
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

    def evict_idle(self) -> list[str]:
        """Kill ffmpeg processes that haven't seen activity recently.

        Returns the list of evicted path_hashes (useful for tests).
        """
        now = time.monotonic()
        stale = self._proc_mgr.stale_hashes(now)
        evicted: list[str] = []
        for path_hash in stale:
            idle_for = now - self._proc_mgr.access_time(path_hash, now)
            _logger.info("Evicting idle ffmpeg for %s (idle %.0fs)", path_hash, idle_for)
            self._kill_processes(path_hash)
            evicted.append(path_hash)
        return evicted

    def evict_lru(self) -> list[str]:
        """Delete least-recently-used cache buckets until within the size limit.

        Returns the list of evicted path_hashes (useful for tests).
        """
        return self._cache_store.evict_lru()

    # -- Public API ------------------------------------------------------------

    def get_path_hash(self, file_path: str, start: int = 0, end: int | None = None) -> str:
        """Get the hash key for a source file at a given start offset.

        Delegates to :class:`HlsCacheStore`. See its docstring for the
        exact bucket-keying contract (deterministic, legacy-compatible at
        ``start=0``/``end=None``).
        """
        return self._cache_store.get_path_hash(file_path, start, end)

    def get_file_by_hash(self, path_hash: str, relative_path: str) -> Path | None:
        """Get any file from cache by hash + relative path.

        Includes path traversal protection via ``Path.is_relative_to``.
        Touches the access timestamp on hit so the eviction loop knows
        the cache is still being consumed by a player.
        """
        return self._cache_store.get_file_by_hash(path_hash, relative_path)

    def is_complete(self, path_hash: str) -> bool:
        """Check if every playlist in the bucket has been sealed with ENDLIST."""
        return self._cache_store.is_complete(path_hash)

    def get_master_playlist(self, path_hash: str) -> str | None:
        """Get master playlist content, falling back to legacy flat playlist.

        Touches access time on hit so the player attaching to a still-warm
        cache resets the idle timer immediately.
        """
        return self._cache_store.get_master_playlist(path_hash)

    def wait_for_subtitle(
        self,
        path_hash: str,
        sub_index: int,
        timeout: float,
    ) -> bool:
        """Block until a specific subtitle has finished extracting.

        Delegates to :class:`SubtitlePipeline`. Returns ``True`` when the
        readiness event fires or the subtitle isn't tracked; ``False``
        only on timeout.
        """
        return self._subtitles.wait_for_subtitle(path_hash, sub_index, timeout)

    def get_cached_tracks(self, path_hash: str) -> dict[str, Any] | None:
        """Get cached probe result from tracks.json."""
        return self._probe_cache.get_cached_tracks(path_hash)

    async def ensure_playlist(self, file_path: str, start: int = 0, end: int | None = None) -> str:
        """Start generation and wait until the first segments are ready.

        Args:
            file_path: Absolute path to the source video file.
            start: Source-time second to begin transcoding at, honoured
                exactly so a forward seek anchors a fresh encode on the
                target second. Callers wanting cache reuse across nearby
                positions quantise ``start`` before calling. ``0`` is the
                legacy behaviour (single bucket per file).
            end: Source-time second to clamp the encode at, for a title
                occupying only a sub-range of a shared physical file
                (ADR-030). ``None`` (the default) encodes to the end of
                the file.

        Returns:
            The path hash for the bucket — unique per ``(file_path,
            start_bucket, end)`` triple.

        Raises:
            RuntimeError: If FFmpeg is not available, fails, or times out.
            FileNotFoundError: If the source file does not exist.
        """
        path_hash = self.get_path_hash(file_path, start, end)
        # Touch immediately so the eviction loop never kills a process
        # that the user just asked for, even if no segments have been
        # served yet (e.g. while waiting for ffmpeg to start).
        self._proc_mgr.touch(path_hash)

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
            await self._generate_and_wait(
                file_path, start, path_hash, force_software=False, end=end
            )
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
            await self._generate_and_wait(file_path, start, path_hash, force_software=True, end=end)
        return path_hash

    def _would_use_hw_transcode(self, file_path: str, start: int) -> bool:
        """Whether the NVENC/CUDA pipeline would be chosen for this request.

        Drives the software-fallback decision: a HW-only failure (CUDA
        init, NVDEC capability, transient GPU contention) recovers on the
        libx264 path, whereas a software failure would just repeat.
        """
        if not self._hw_probe.use_nvenc():
            return False
        if start > 0:
            return True
        return self._hw_probe.probe_video_codec(file_path) not in BROWSER_SAFE_CODECS

    async def _generate_and_wait(
        self,
        file_path: str,
        start: int,
        path_hash: str,
        *,
        force_software: bool,
        end: int | None = None,
    ) -> None:
        """Start generation and block until the first segments are ready.

        Raises:
            RuntimeError: if the ffmpeg process fails or no segments
                appear within the poll timeout.
        """
        await asyncio.to_thread(self._start_generation, file_path, start, force_software, end)

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

            main_proc = self._proc_mgr.get_main_process(path_hash)
            if main_proc and main_proc.poll() is not None:
                self._handle_generation_failure(path_hash, main_proc)

            await asyncio.sleep(_POLL_INTERVAL)

        msg = f"Timeout waiting for HLS segments ({_POLL_TIMEOUT}s)"
        raise RuntimeError(msg)

    def probe_tracks(self, file_path: str) -> ProbeResult:
        """Probe a file for tracks, using cache when available.

        Image-based subtitles that have an OCR sidecar on disk are
        surfaced as external text tracks (ADR-027); a no-op when subtitle
        OCR is disabled. Applied on the base probe (cached without OCR
        tracks) so the derivation stays idempotent across cache hits.
        """
        path_hash = self.get_path_hash(file_path)
        cached = self.get_cached_tracks(path_hash)
        base = self._probe_cache.deserialize(cached) if cached else self._probe.probe(file_path)
        return attach_ocr_subtitles(
            base, file_path, self._runtime_settings.subtitle_ocr_snapshot_sync()
        )

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
            for path_hash in self._proc_mgr.active_hashes():
                self._kill_processes(path_hash)
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_store.touch_last_cleared_marker()

    def get_cache_stats(self) -> HlsCacheStats:
        """Return total bytes on disk + the configured ceiling + last clear."""
        return self._cache_store.get_cache_stats()

    # -- Private: process management -------------------------------------------

    def _kill_processes(self, path_hash: str) -> None:
        """Kill all running FFmpeg processes for a path hash.

        Also releases any waiters parked on subtitle readiness events for
        this bucket so they don't block their full timeout after we've
        already torn down the cache.

        Atomic across both collaborators: the shared reentrant lock is
        held while the process registry is popped/killed and the subtitle
        pipeline releases its waiters, so no concurrent generation can
        interleave between the two.
        """
        with self._lock:
            procs = self._proc_mgr.pop(path_hash)
            for proc in procs:
                if proc.poll() is None:
                    proc.kill()
            self._subtitles.release(path_hash)

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
        self,
        file_path: str,
        start: int = 0,
        force_software: bool = False,
        end: int | None = None,
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
            end: Source-time second to clamp the encode at, for a title
                occupying only a sub-range of a shared file (ADR-030), or
                ``None`` to encode to the end of the file.
        """
        source = self._validate_source(file_path)
        safe_path = str(source)
        path_hash = self.get_path_hash(file_path, start, end)
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
        # Read-time view with OCR text tracks surfaced for image subtitles
        # that already have a sidecar (ADR-027). The base ``probe_result``
        # is what gets cached; ``probe_view`` (which may carry the derived
        # OCR tracks) drives subtitle rendition + master playlist so the
        # ``sub_N`` indices match ``probe_tracks``. A no-op when disabled.
        probe_view = attach_ocr_subtitles(
            probe_result, safe_path, self._runtime_settings.subtitle_ocr_snapshot_sync()
        )

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
            for s in probe_view.all_subtitles
            if s.is_text_based and (not s.is_external or s.file_path is not None)
        ]

        with self._lock:
            # Re-check after acquiring lock
            if self.is_complete(path_hash):
                return path_hash

            if self._proc_mgr.running_procs(path_hash):
                return path_hash
            self._proc_mgr.discard(path_hash)

            # Clean stale cache
            output_dir = self._cache_dir / path_hash
            if output_dir.exists():
                _logger.info("Cleaning stale cache for %s", path_hash)
                shutil.rmtree(output_dir, ignore_errors=True)

            output_dir.mkdir(parents=True, exist_ok=True)
            self._probe_cache.save(output_dir, probe_result)

            procs: list[subprocess.Popen[bytes]] = []

            # 1. Main: video + default audio (always first in list)
            video_dir = output_dir / _VIDEO_DIR
            video_dir.mkdir()
            cmd = with_ffmpeg_threads(
                self._cmd_builder.build_video_cmd(
                    safe_path, video_dir, probe_result, bucket_start, force_software, end
                ),
                ffmpeg_threads,
            )
            _logger.info("Starting video HLS for %s (offset=%ds)", safe_path, bucket_start)
            procs.append(
                self._spawn_ffmpeg(cmd, playlist_path=video_dir / "playlist.m3u8"),
            )

            # 2. Additional audio tracks (audio-only HLS)
            primary_audio_idx = primary_audio_index(probe_result)
            for track in probe_result.audio_tracks:
                if track.index == primary_audio_idx:
                    continue
                audio_dir = output_dir / f"audio_{track.index}"
                audio_dir.mkdir()
                cmd = with_ffmpeg_threads(
                    self._cmd_builder.build_audio_cmd(
                        safe_path, audio_dir, track, bucket_start, end
                    ),
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
            # so racing them against playback start is safe. Uses ``probe_view``
            # so surfaced OCR text tracks (ADR-027) get a ``sub_N`` rendition
            # matching ``text_subs``.
            self._master_writer.write(output_dir, probe_view)

            # 4. Pre-create per-subtitle readiness events. They MUST be
            # registered before _start_generation returns so the file
            # route can find them the instant the player picks a track.
            self._subtitles.register(path_hash, [sub.index for sub in text_subs])

            self._proc_mgr.register(path_hash, procs)

        # 5. Extract each subtitle in its own background thread. Running
        # them in parallel (instead of one big serial thread) means a
        # user-selected subtitle only waits for its own ffmpeg, not for
        # every other track that happens to be earlier in the list.
        for sub in text_subs:
            threading.Thread(
                target=self._subtitles.extract_one,
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

    # -- Private: validation ---------------------------------------------------

    @staticmethod
    def _validate_source(file_path: str) -> Path:
        """Resolve and validate that file_path is an existing file."""
        resolved = Path(file_path).resolve()
        if not resolved.is_file():
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg)
        return resolved


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


__all__ = ["HlsService"]
