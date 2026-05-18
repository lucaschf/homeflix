"""Tests for GetHlsCacheStatsUseCase."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.modules.media.application.ports.hls_playlist_port import (
    HlsCacheStats,
    HlsPlaylistPort,
)
from src.modules.media.application.use_cases.get_hls_cache_stats import (
    GetHlsCacheStatsUseCase,
)


@pytest.mark.unit
class TestGetHlsCacheStatsUseCase:
    def test_should_return_stats_from_port(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        snapshot = HlsCacheStats(
            size_bytes=1234,
            max_bytes=5000,
            last_cleared_at=datetime(2026, 5, 17, 10, 0, tzinfo=UTC),
        )
        hls.get_cache_stats.return_value = snapshot

        result = GetHlsCacheStatsUseCase(hls=hls).execute()

        assert result is snapshot
        hls.get_cache_stats.assert_called_once_with()

    def test_should_pass_through_none_last_cleared(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.get_cache_stats.return_value = HlsCacheStats(
            size_bytes=0,
            max_bytes=10,
            last_cleared_at=None,
        )

        result = GetHlsCacheStatsUseCase(hls=hls).execute()

        assert result.last_cleared_at is None
