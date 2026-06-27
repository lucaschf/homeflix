"""Unit tests for GetOverviewStatsUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.ports.hls_playlist_port import HlsCacheStats
from src.modules.media.application.use_cases.get_overview_stats import (
    GetOverviewStatsUseCase,
)
from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId


def _media_uow_factory(
    *,
    movies_count: int,
    series_count: int,
    last_scan: ScanRun | None,
) -> MagicMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.movies.count.return_value = movies_count
    uow.series = AsyncMock()
    uow.series.count.return_value = series_count
    uow.scan_runs = AsyncMock()
    uow.scan_runs.list_paginated.return_value = [last_scan] if last_scan else []
    return MagicMock(return_value=uow)


def _user_count_port(users_count: int) -> MagicMock:
    port = MagicMock()
    port.count_users = AsyncMock(return_value=users_count)
    return port


pytestmark = pytest.mark.unit


class TestGetOverviewStatsUseCase:
    async def test_should_aggregate_every_card_into_one_response(self) -> None:
        last_scan = ScanRun(
            id=ScanRunId.generate(),
            kind=ScanRunKind.SCAN,
            trigger=ScanRunTrigger.MANUAL,
            library_id="lib_test12345678",
            started_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 18, 10, 5, tzinfo=UTC),
            status=ScanRunStatus.SUCCEEDED,
        )
        review_uc = AsyncMock()
        review_uc.execute.return_value = MagicMock(movies=[1, 2, 3])  # 3-row list
        hls = MagicMock()
        hls.get_cache_stats.return_value = HlsCacheStats(
            size_bytes=100,
            max_bytes=1000,
            last_cleared_at=None,
        )

        result = await GetOverviewStatsUseCase(
            media_uow_factory=_media_uow_factory(
                movies_count=42,
                series_count=7,
                last_scan=last_scan,
            ),
            user_count=_user_count_port(users_count=4),
            list_movies_needing_review=review_uc,
            hls_playlist=hls,
        ).execute()

        assert result.movies_count == 42
        assert result.series_count == 7
        assert result.users_count == 4
        assert result.review_count == 3
        assert result.last_scan is not None
        assert result.last_scan.status == "succeeded"
        assert result.last_scan.id == str(last_scan.id)
        assert result.hls_cache.size_bytes == 100
        assert result.hls_cache.max_bytes == 1000

    async def test_should_return_null_last_scan_when_no_scans_recorded(self) -> None:
        review_uc = AsyncMock()
        review_uc.execute.return_value = MagicMock(movies=[])
        hls = MagicMock()
        hls.get_cache_stats.return_value = HlsCacheStats(
            size_bytes=0,
            max_bytes=1000,
            last_cleared_at=None,
        )

        result = await GetOverviewStatsUseCase(
            media_uow_factory=_media_uow_factory(
                movies_count=0,
                series_count=0,
                last_scan=None,
            ),
            user_count=_user_count_port(users_count=1),
            list_movies_needing_review=review_uc,
            hls_playlist=hls,
        ).execute()

        assert result.last_scan is None
        assert result.review_count == 0
