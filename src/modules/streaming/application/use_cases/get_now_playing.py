"""Use case: list active HLS playback sessions for the admin dashboard.

Reads the in-memory now-playing registry, resolves the watching
profiles' display names via the identity ACL, and derives a percent
progress per session plus the aggregate uplink.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.streaming.application.dtos.now_playing_dtos import (
    NowPlayingOutput,
    NowPlayingSessionOutput,
)

if TYPE_CHECKING:
    from src.modules.streaming.application.ports.now_playing_port import NowPlayingPort
    from src.modules.streaming.application.ports.profile_summary_port import (
        ProfileSummaryPort,
    )


class GetNowPlayingUseCase:
    """Snapshot of what's playing on the server right now."""

    def __init__(
        self,
        now_playing: NowPlayingPort,
        profile_summary: ProfileSummaryPort,
    ) -> None:
        self._now_playing = now_playing
        self._profiles = profile_summary

    async def execute(self) -> NowPlayingOutput:
        """Return the live sessions enriched with profile names + pct."""
        sessions = self._now_playing.active()
        names = await self._profiles.names_for(
            [s.profile_id for s in sessions if s.profile_id],
        )

        rows: list[NowPlayingSessionOutput] = []
        for session in sessions:
            pct = 0
            if session.duration_seconds and session.duration_seconds > 0:
                ratio = session.position_seconds / session.duration_seconds
                pct = max(0, min(100, round(ratio * 100)))
            rows.append(
                NowPlayingSessionOutput(
                    profile_id=session.profile_id,
                    profile_name=names.get(session.profile_id) if session.profile_id else None,
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
                    position_seconds=session.position_seconds,
                    duration_seconds=session.duration_seconds,
                    pct=pct,
                    mbps=session.mbps,
                ),
            )

        total_mbps = round(sum(session.mbps for session in sessions), 1)
        return NowPlayingOutput(sessions=rows, total_mbps=total_mbps)
