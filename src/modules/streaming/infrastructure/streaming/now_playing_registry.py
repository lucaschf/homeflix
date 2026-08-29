"""In-memory registry of active HLS playback sessions.

Powers the admin "Reproduzindo agora" (now playing) dashboard. The
registry is fed by *purely observational* hooks bolted onto the
streaming path — generating a playlist and serving a segment each emit
a note here, but neither the playlist bytes nor the segment bytes nor
the ffmpeg pipeline change in any way. Every write is best-effort:
callers wrap notes so a bug in dashboard bookkeeping can never break a
stream.

Sessions are keyed by ``path_hash`` (the same hash the HLS cache uses),
so two viewers of the byte-identical file at the same ``start`` collapse
into one row — an accepted limitation for a household server, where
concurrent identical-file playback is rare. Different files (or a seek,
which mints a new ``start`` bucket) get their own rows.

State is in-memory and ephemeral: a backend restart clears it, which is
correct for a "right now" view. Liveness is driven by segment requests
(roughly one every ``_SEGMENT_DURATION`` seconds during playback); a
session with no segment activity within ``_FRESHNESS_WINDOW`` is
considered ended and pruned on the next read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

from src.modules.streaming.application.ports.now_playing_port import (
    NowPlayingPort,
    NowPlayingSession,
)

# A session counts as live while its newest segment request is within
# this window. Kept comfortably above the 10 s segment cadence so a
# brief network stall doesn't flap a steady stream out of the list.
_FRESHNESS_WINDOW = 25.0
# Seconds of wall-clock playback each segment represents. Mirrors
# ``HlsService._SEGMENT_DURATION`` — keep the two in sync.
_SEGMENT_DURATION = 10
# Rolling window (seconds) used to estimate the *current* bitrate from
# recently-served segment bytes, rather than a whole-session average.
_BITRATE_WINDOW = 12.0


@dataclass
class _LiveSession:
    """Mutable bookkeeping for one in-flight playback session."""

    path_hash: str
    started_at: float
    last_seen: float
    # Identity + media context, captured when the playlist is built.
    profile_id: str | None = None
    media_id: str | None = None
    media_kind: str | None = None  # "movie" | "episode"
    title: str | None = None
    year: int | None = None
    meta: str | None = None
    poster_url: str | None = None
    ip: str | None = None
    device: str | None = None
    duration_seconds: int | None = None
    start_offset: int = 0
    # Technical mode, stamped by the HLS service when it decides.
    mode: str | None = None  # "direct" | "transcode"
    detail: str | None = None
    # Progress + bitrate signals, driven by segment requests.
    max_segment_index: int = 0
    # (monotonic_ts, bytes) samples for the rolling bitrate estimate.
    byte_samples: list[tuple[float, int]] = field(default_factory=list)


class NowPlayingRegistry(NowPlayingPort):
    """Thread-safe, in-memory store of active playback sessions.

    A process-wide singleton (one ffmpeg fleet, one cache) shared by
    the streaming routes and the HLS service. All public methods are
    cheap and lock-guarded; the write methods never raise on bad input
    (callers still wrap them defensively).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _LiveSession] = {}
        self._lock = Lock()

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _ensure(self, path_hash: str) -> _LiveSession:
        session = self._sessions.get(path_hash)
        if session is None:
            now = self._now()
            session = _LiveSession(path_hash=path_hash, started_at=now, last_seen=now)
            self._sessions[path_hash] = session
        return session

    def note_view(
        self,
        path_hash: str,
        *,
        profile_id: str | None = None,
        media_id: str | None = None,
        media_kind: str | None = None,
        title: str | None = None,
        year: int | None = None,
        meta: str | None = None,
        poster_url: str | None = None,
        ip: str | None = None,
        device: str | None = None,
        duration_seconds: int | None = None,
        start_offset: int = 0,
    ) -> None:
        """Record the identity + media context for a playlist request.

        Called when a master playlist is generated, where the caller
        knows who is watching and what. Refreshes ``last_seen`` so the
        session is live from the moment playback starts, before the
        first segment lands.
        """
        with self._lock:
            session = self._ensure(path_hash)
            session.last_seen = self._now()
            session.profile_id = profile_id
            session.media_id = media_id
            session.media_kind = media_kind
            session.title = title
            session.year = year
            session.meta = meta
            session.poster_url = poster_url
            session.ip = ip
            session.device = device
            session.duration_seconds = duration_seconds
            session.start_offset = start_offset

    def note_mode(self, path_hash: str, mode: str, detail: str | None = None) -> None:
        """Stamp the decided playback mode (``direct``/``transcode``)."""
        with self._lock:
            session = self._ensure(path_hash)
            session.mode = mode
            session.detail = detail

    def note_segment(
        self,
        path_hash: str,
        byte_count: int,
        segment_index: int | None = None,
    ) -> None:
        """Record a served segment — liveness, bitrate bytes, progress."""
        with self._lock:
            session = self._ensure(path_hash)
            now = self._now()
            session.last_seen = now
            if byte_count > 0:
                session.byte_samples.append((now, byte_count))
            if segment_index is not None and segment_index > session.max_segment_index:
                session.max_segment_index = segment_index

    def _rolling_mbps(self, session: _LiveSession, now: float) -> float:
        cutoff = now - _BITRATE_WINDOW
        recent = [(ts, n) for ts, n in session.byte_samples if ts >= cutoff]
        session.byte_samples = recent
        if not recent:
            return 0.0
        total_bytes = sum(n for _, n in recent)
        span = max(now - recent[0][0], 1.0)
        return round((total_bytes * 8) / (span * 1_000_000), 1)

    def active(self) -> list[NowPlayingSession]:
        """Return live sessions, pruning any past the freshness window.

        Computes a rolling bitrate and a segment-derived playback
        position per session. Position is approximate — the player
        buffers ahead, so it leans slightly optimistic — and is clamped
        to the media duration.
        """
        now = self._now()
        snapshots: list[NowPlayingSession] = []
        with self._lock:
            stale = [h for h, s in self._sessions.items() if now - s.last_seen > _FRESHNESS_WINDOW]
            for path_hash in stale:
                del self._sessions[path_hash]

            for session in self._sessions.values():
                # Skip sessions that only ever saw segment requests (no
                # playlist note): e.g. a stream that survived a backend
                # restart keeps fetching segments but never re-requests
                # the playlist, so we have bytes but no identity. Better
                # to hide the ghost row than show a "—" with no watcher.
                if session.media_id is None:
                    continue
                position = session.start_offset + session.max_segment_index * _SEGMENT_DURATION
                if session.duration_seconds is not None:
                    position = min(position, session.duration_seconds)
                snapshots.append(
                    NowPlayingSession(
                        profile_id=session.profile_id,
                        media_id=session.media_id,
                        media_kind=session.media_kind,
                        title=session.title,
                        year=session.year,
                        meta=session.meta,
                        poster_url=session.poster_url,
                        ip=session.ip,
                        device=session.device,
                        mode=session.mode,
                        detail=session.detail,
                        position_seconds=position,
                        duration_seconds=session.duration_seconds,
                        mbps=self._rolling_mbps(session, now),
                    )
                )
        snapshots.sort(key=lambda s: (s.title or "").lower())
        return snapshots
