"""FFmpeg subprocess registry for the HLS cache.

Extracted from ``HlsService``. Owns the live ffmpeg process handles and
their per-bucket last-access timestamps, guarded by a *shared* reentrant
lock. The lock is injected (not created here) so the orchestrator can
hold it while coordinating this manager and the subtitle pipeline inside
one atomic critical section — the reentrancy is what lets a collaborator
method re-acquire the lock the orchestrator already holds.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess
    import threading


class FfmpegProcessManager:
    """Track spawned ffmpeg processes and their bucket access times.

    Args:
        lock: The shared :class:`threading.RLock` guarding all HLS
            process/subtitle state. Injected so this manager, the
            subtitle pipeline, and the orchestrator all serialise on
            the *same* reentrant lock.
        idle_timeout: Seconds without activity before a bucket's ffmpeg
            processes count as idle in :meth:`stale_hashes`.
    """

    def __init__(self, lock: threading.RLock, idle_timeout: float) -> None:
        self._lock = lock
        self._idle_timeout = idle_timeout
        self._processes: dict[str, list[subprocess.Popen[bytes]]] = {}
        # path_hash → monotonic timestamp of the most recent activity
        # (playlist request OR segment fetch). The eviction loop reads
        # this to decide which ffmpeg processes are idle.
        self._last_access: dict[str, float] = {}

    def touch(self, path_hash: str) -> None:
        """Record that this cache bucket was just used."""
        with self._lock:
            self._last_access[path_hash] = time.monotonic()

    def register(self, path_hash: str, procs: list[subprocess.Popen[bytes]]) -> None:
        """Register a bucket's spawned processes and stamp its access time."""
        with self._lock:
            self._processes[path_hash] = procs
            self._last_access[path_hash] = time.monotonic()

    def discard(self, path_hash: str) -> None:
        """Drop any stale process list for a bucket without killing it.

        Used just before a fresh generation registers new processes, to
        clear an entry left by a prior run whose handles are all dead.
        """
        with self._lock:
            self._processes.pop(path_hash, None)

    def pop(self, path_hash: str) -> list[subprocess.Popen[bytes]]:
        """Remove a bucket's processes and access time, returning the procs.

        The caller kills the returned handles outside the manager so the
        process-list pop and the subtitle release can be sequenced by the
        orchestrator under the shared lock.
        """
        with self._lock:
            procs = self._processes.pop(path_hash, [])
            self._last_access.pop(path_hash, None)
        return procs

    def forget_access(self, path_hash: str) -> None:
        """Drop a bucket's last-access entry (after LRU disk eviction)."""
        with self._lock:
            self._last_access.pop(path_hash, None)

    def running_procs(self, path_hash: str) -> list[subprocess.Popen[bytes]]:
        """Return the still-running processes registered for a bucket."""
        with self._lock:
            return [p for p in self._processes.get(path_hash, []) if p.poll() is None]

    def get_main_process(self, path_hash: str) -> subprocess.Popen[bytes] | None:
        """Get the main (video) FFmpeg process for a generation, if any."""
        with self._lock:
            procs = self._processes.get(path_hash, [])
        return procs[0] if procs else None

    def is_active(self, path_hash: str) -> bool:
        """Whether a bucket currently has registered ffmpeg processes."""
        with self._lock:
            return path_hash in self._processes

    def active_hashes(self) -> list[str]:
        """Snapshot the path hashes with registered processes, under lock."""
        with self._lock:
            return list(self._processes)

    def access_time(self, path_hash: str, default: float) -> float:
        """Read a bucket's last-access time, or ``default`` if untracked."""
        with self._lock:
            return self._last_access.get(path_hash, default)

    def stale_hashes(self, now: float) -> list[str]:
        """Path hashes idle longer than the timeout that still have processes."""
        with self._lock:
            return [
                ph
                for ph, last in self._last_access.items()
                if now - last > self._idle_timeout and ph in self._processes
            ]


__all__ = ["FfmpegProcessManager"]
