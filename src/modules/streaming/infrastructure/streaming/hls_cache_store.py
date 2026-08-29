"""On-disk HLS cache bucket store.

Extracted from ``HlsService``. Owns the cache-root filesystem: bucket
hashing, completeness checks, file/master-playlist reads (touching the
access clock on hits), LRU disk eviction, and the global-clear marker.

Reads of live process state (which buckets are active, their last-access
time) go through the injected :class:`FfmpegProcessManager` so this store
never touches the shared lock directly.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.modules.streaming.application.ports.hls_playlist_port import HlsCacheStats
from src.modules.streaming.infrastructure.streaming._hls_common import (
    _EVICTING_PREFIX,
    _VIDEO_DIR,
    _has_endlist,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.streaming.application.ports.runtime_config_ports import HlsRuntimeConfigPort
    from src.modules.streaming.infrastructure.streaming.ffmpeg_process_manager import (
        FfmpegProcessManager,
    )

_logger = logging.getLogger(__name__)


class HlsCacheStore:
    """Read, hash, and evict HLS cache buckets under a cache root.

    Args:
        cache_dir: Root cache directory; each bucket lives at
            ``<cache_dir>/<path_hash>/``.
        runtime_settings: Snapshot facade for the cache-size ceiling.
        process_manager: Registry consulted for which buckets are active
            and their last-access times during LRU eviction, and touched
            on file/playlist hits.
    """

    def __init__(
        self,
        cache_dir: Path,
        runtime_settings: HlsRuntimeConfigPort,
        process_manager: FfmpegProcessManager,
    ) -> None:
        self._cache_dir = cache_dir
        self._runtime_settings = runtime_settings
        self._process_manager = process_manager

    def get_path_hash(self, file_path: str, start: int = 0, end: int | None = None) -> str:
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
            end: Source-time second the encode is clamped to end at, for a
                title that occupies only a sub-range of a shared physical
                file (ADR-030). ``None`` (the default) encodes to the end
                of the file. Folded into the hash so two episodes sharing
                one file get distinct buckets.

        Returns:
            Hex MD5 digest uniquely identifying the cache bucket. The
            seek-ahead and resume flows on cold cache rely on this
            being deterministic so the same offset always re-attaches
            to the same on-disk bucket.
        """
        key = file_path if start == 0 and end is None else f"{file_path}:{start}:{end}"
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
        self._process_manager.touch(path_hash)
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

        # The bucket is only reusable if the root master.m3u8 that
        # get_master_playlist actually serves is present and non-empty.
        # Without this guard a bucket whose nested playlists are sealed
        # but whose master was lost — e.g. a partial rmtree that skipped
        # a momentarily-locked file during LRU eviction — looks
        # "complete", short-circuits regeneration in ensure_playlist, and
        # then 404s forever on the missing master. Treating it as
        # incomplete makes the next request regenerate and self-heal.
        master = bucket / "master.m3u8"
        try:
            if not master.is_file() or master.stat().st_size == 0:
                return False
        except OSError:
            return False

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
                self._process_manager.touch(path_hash)
                return content
        return None

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
            if entry.name.startswith(_EVICTING_PREFIX):
                # Leftover from a prior cleanup whose delete was blocked
                # (locked file). Retry it now and never count it as a bucket.
                shutil.rmtree(entry, ignore_errors=True)
                continue
            path_hash = entry.name
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            total_size += size
            # Prefer in-memory access time; fall back to directory mtime
            access_time = self._process_manager.access_time(path_hash, entry.stat().st_mtime)
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
            if self._process_manager.is_active(path_hash):
                continue
            bucket_path = self._cache_dir / path_hash
            _logger.info(
                "LRU evicting cache bucket %s (%.1f MB)",
                path_hash,
                size / (1024 * 1024),
            )
            if not self._remove_bucket_dir(bucket_path):
                # A locked file blocked the atomic rename — the bucket is
                # still fully intact. Leave it and retry next sweep rather
                # than risk a partial delete; the cache stays briefly over
                # budget, which is harmless.
                continue
            self._process_manager.forget_access(path_hash)
            total_size -= size
            evicted.append(path_hash)
        return evicted

    def _remove_bucket_dir(self, bucket_path: Path) -> bool:
        """Remove a bucket directory without ever exposing a partial state.

        Renames the bucket out of the live cache path in a single atomic
        ``rename`` and only then deletes the renamed copy best-effort. A
        reader therefore sees the bucket either fully present or fully
        gone — never half-deleted. This is what closes the whole class of
        partial-eviction zombies: a momentarily locked file (an AV scan
        or the Windows indexer holding a segment) can no longer strand a
        bucket with, say, its ``master.m3u8`` deleted but its nested
        playlists intact, a state ``ensure_playlist`` would treat as
        complete and then 404 on forever.

        Args:
            bucket_path: The live bucket directory to remove.

        Returns:
            ``True`` if the bucket left the live path (rename succeeded,
            or it was already gone); ``False`` if a lock blocked the
            rename and the bucket is still fully intact — the caller
            should treat that as "not evicted" and retry on a later sweep.
        """
        if not bucket_path.exists():
            return True
        trash = bucket_path.with_name(f"{_EVICTING_PREFIX}{bucket_path.name}")
        # A leftover trash dir from a previous blocked cleanup would make
        # the rename target already exist; clear it first (best-effort).
        if trash.exists():
            shutil.rmtree(trash, ignore_errors=True)
        try:
            bucket_path.rename(trash)
        except OSError:
            return False
        shutil.rmtree(trash, ignore_errors=True)
        return True

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

    def touch_last_cleared_marker(self) -> None:
        """Stamp the global-clear marker's mtime to now (best-effort)."""
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


__all__ = ["HlsCacheStore"]
