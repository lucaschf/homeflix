"""Port for the in-memory now-playing session registry.

The streaming use cases write to it (a playlist request notes who/what,
a segment request notes liveness + bytes); the admin read use case
lists active sessions. The implementation lives in
``media.infrastructure.streaming.now_playing_registry`` and is purely
observational — it never alters what the player receives.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class NowPlayingViewContext:
    """Identity + media context captured when a playlist is generated.

    Built by the streaming routes (which know the caller's profile,
    client IP/device and the resolved title) and threaded into the
    playlist use case, which owns the ``path_hash`` the registry keys on.
    """

    profile_id: str | None = None
    media_id: str | None = None
    media_kind: str | None = None
    title: str | None = None
    year: int | None = None
    meta: str | None = None
    poster_url: str | None = None
    ip: str | None = None
    device: str | None = None
    duration_seconds: int | None = None


@dataclass(frozen=True)
class NowPlayingSession:
    """Immutable snapshot of one live playback session.

    Attributes:
        profile_id: Watching profile (``prf_xxx``), or ``None`` if the
            view note never carried one.
        media_id: Movie / series id behind the stream.
        media_kind: ``"movie"`` or ``"episode"``.
        title: Display title captured at playlist time.
        year: Release year, when known.
        meta: Secondary line — resolution for movies, ``"T1 · E3"`` for
            episodes.
        poster_url: Poster path, reused as-is by the client.
        ip: Client IP seen on the playlist request.
        device: Shortened User-Agent of the player.
        mode: ``"direct"`` / ``"transcode"`` once the service stamps it;
            ``None`` until then.
        detail: Optional technical detail (e.g. source→target codec).
        position_seconds: Approximate playhead, derived from the newest
            requested segment (leans slightly ahead of the real
            position because the player buffers).
        duration_seconds: Total runtime, when known.
        mbps: Rolling-window estimate of the current uplink in Mbps.
    """

    profile_id: str | None
    media_id: str | None
    media_kind: str | None
    title: str | None
    year: int | None
    meta: str | None
    poster_url: str | None
    ip: str | None
    device: str | None
    mode: str | None
    detail: str | None
    position_seconds: int
    duration_seconds: int | None
    mbps: float


class NowPlayingPort(ABC):
    """Records and reports active HLS playback sessions."""

    @abstractmethod
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
        """Record the identity + media context for a playlist request."""

    @abstractmethod
    def note_mode(self, path_hash: str, mode: str, detail: str | None = None) -> None:
        """Stamp the decided playback mode for a session."""

    @abstractmethod
    def note_segment(
        self,
        path_hash: str,
        byte_count: int,
        segment_index: int | None = None,
    ) -> None:
        """Record a served segment (liveness + bytes + progress)."""

    @abstractmethod
    def active(self) -> list[NowPlayingSession]:
        """Return live sessions, pruning any past the freshness window."""


__all__ = ["NowPlayingPort", "NowPlayingSession", "NowPlayingViewContext"]
