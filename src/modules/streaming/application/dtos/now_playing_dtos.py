"""Output DTOs for the admin now-playing endpoint."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NowPlayingSessionOutput:
    """One active playback session as surfaced to the admin dashboard."""

    profile_id: str | None
    profile_name: str | None
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
    pct: int
    mbps: float


@dataclass(frozen=True)
class NowPlayingOutput:
    """The full now-playing snapshot: sessions + aggregate uplink."""

    sessions: list[NowPlayingSessionOutput]
    total_mbps: float
