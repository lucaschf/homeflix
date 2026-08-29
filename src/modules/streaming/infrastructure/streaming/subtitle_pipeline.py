"""Background subtitle extraction and readiness signalling for HLS.

Extracted from ``HlsService``. Owns the per-bucket subtitle readiness
events and runs the ffmpeg-to-WebVTT extraction for each text track in
its own worker thread. The readiness events are guarded by the *shared*
reentrant lock (injected) so ``HlsService`` can register or release them
atomically alongside the ffmpeg process registry.

The WebVTT post-processing helpers (bucket-local cue shift, HLS
timestamp-map header, atomic locked-replace write, wrapper playlist)
live here rather than on ``hls_service`` so this pipeline is
self-contained and imports no orchestrator symbol back.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
import uuid
from typing import TYPE_CHECKING

from src.modules.streaming.infrastructure.streaming._subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.streaming.application.ports.runtime_config_ports import HlsRuntimeConfigPort
    from src.shared_kernel.value_objects.tracks import SubtitleTrack

_logger = logging.getLogger(__name__)


class SubtitlePipeline:
    """Extract text subtitles to WebVTT and signal per-track readiness.

    Args:
        lock: The shared :class:`threading.RLock` guarding all HLS
            process/subtitle state. Injected so the orchestrator can
            register or release readiness events atomically with the
            ffmpeg process registry.
        cache_dir: Root cache directory (unused directly today but kept
            for symmetry with the other collaborators and future use).
        runtime_settings: Snapshot facade used to read ``ffmpeg_threads``
            fresh per subtitle ffmpeg invocation.
    """

    def __init__(
        self,
        lock: threading.RLock,
        cache_dir: Path,
        runtime_settings: HlsRuntimeConfigPort,
    ) -> None:
        self._lock = lock
        self._cache_dir = cache_dir
        self._runtime_settings = runtime_settings
        # path_hash → {subtitle_index: Event}. Set when a subtitle's
        # background extraction finishes (success or failure). The file
        # route uses these to block its response until the requested
        # subtitle is on disk, instead of returning a premature 404.
        self._subtitle_events: dict[str, dict[int, threading.Event]] = {}

    def register(self, path_hash: str, indices: list[int]) -> None:
        """Pre-create per-subtitle readiness events for a bucket.

        Registered before generation returns so the file route can find
        an event the instant the player picks a track.
        """
        if not indices:
            return
        with self._lock:
            self._subtitle_events[path_hash] = {index: threading.Event() for index in indices}

    def release(self, path_hash: str) -> None:
        """Release any waiters parked on this bucket's subtitle events.

        Pops the events dict under the lock and sets each event so a
        route blocked in :meth:`wait_for_subtitle` wakes immediately
        instead of blocking its full timeout after teardown.
        """
        with self._lock:
            events = self._subtitle_events.pop(path_hash, {})
        for event in events.values():
            event.set()

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

    def extract_one(
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


__all__ = [
    "SubtitlePipeline",
    "_atomic_write_text",
    "_ensure_vtt_timestamp_map",
    "_shift_webvtt_to_bucket_local",
]
