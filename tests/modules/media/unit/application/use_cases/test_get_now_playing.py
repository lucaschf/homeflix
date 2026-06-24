"""Tests for GetNowPlayingUseCase."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.ports.now_playing_port import NowPlayingSession
from src.modules.media.application.use_cases.get_now_playing import (
    GetNowPlayingUseCase,
)


def _session(**overrides: Any) -> NowPlayingSession:
    base: dict[str, Any] = {
        "profile_id": "prf_1",
        "media_id": "mov_1",
        "media_kind": "movie",
        "title": "Inception",
        "year": 2010,
        "meta": "2160p",
        "poster_url": None,
        "ip": "192.168.0.2",
        "device": "Chrome",
        "mode": None,
        "detail": None,
        "position_seconds": 500,
        "duration_seconds": 1000,
        "mbps": 8.0,
    }
    base.update(overrides)
    return NowPlayingSession(**base)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enriches_name_pct_and_total() -> None:
    now_playing = MagicMock()
    now_playing.active.return_value = [_session(mbps=8.0), _session(mbps=2.0)]
    profiles = AsyncMock()
    profiles.names_for.return_value = {"prf_1": "Lucas"}

    use_case = GetNowPlayingUseCase(now_playing=now_playing, profile_summary=profiles)
    out = await use_case.execute()

    assert out.total_mbps == 10.0
    assert out.sessions[0].profile_name == "Lucas"
    assert out.sessions[0].pct == 50  # 500 / 1000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_when_nobody_watching() -> None:
    now_playing = MagicMock()
    now_playing.active.return_value = []
    profiles = AsyncMock()
    profiles.names_for.return_value = {}

    out = await GetNowPlayingUseCase(
        now_playing=now_playing,
        profile_summary=profiles,
    ).execute()

    assert out.sessions == []
    assert out.total_mbps == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pct_zero_without_duration() -> None:
    now_playing = MagicMock()
    now_playing.active.return_value = [_session(duration_seconds=None)]
    profiles = AsyncMock()
    profiles.names_for.return_value = {"prf_1": "Lucas"}

    out = await GetNowPlayingUseCase(
        now_playing=now_playing,
        profile_summary=profiles,
    ).execute()

    assert out.sessions[0].pct == 0
