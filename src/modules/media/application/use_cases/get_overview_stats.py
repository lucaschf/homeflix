"""GetOverviewStatsUseCase — single aggregator for the admin dashboard."""

from src.modules.media.application.dtos.overview_stats_dtos import (
    HlsCacheSnapshot,
    LastScanSnapshot,
    OverviewStatsOutput,
)
from src.modules.media.application.ports import HlsPlaylistPort
from src.modules.media.application.ports.identity_user_count_port import (
    IdentityUserCountPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.list_movies_needing_review import (
    ListMoviesNeedingReviewUseCase,
)
from src.modules.media.domain.entities.scan_run import ScanRunKind


class GetOverviewStatsUseCase:
    """Aggregate every stat card on the admin Overview into one shot.

    The dashboard renders five "headline" cards (movies count,
    series count, users count, review queue length, last scan)
    plus an HLS occupancy card. Hitting one endpoint instead of
    five keeps the cards in lockstep — no flicker as individual
    queries resolve — and saves a few request round-trips.

    All reads are non-deleted-only. The cross-BC users count goes
    through ``IdentityUserCountPort`` (an ACL adapter), so this use
    case never imports Identity's Unit of Work (ADR-009).
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        user_count: IdentityUserCountPort,
        list_movies_needing_review: ListMoviesNeedingReviewUseCase,
        hls_playlist: HlsPlaylistPort,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._user_count = user_count
        self._list_review = list_movies_needing_review
        self._hls = hls_playlist

    async def execute(self) -> OverviewStatsOutput:
        """Read every card's underlying datum and pack the response."""
        async with self._media_uow_factory() as media_uow:
            movies_count = await media_uow.movies.count()
            series_count = await media_uow.series.count()
            recent_scans = await media_uow.scan_runs.list_paginated(
                kind=ScanRunKind.SCAN,
                limit=1,
            )

        users_count = await self._user_count.count_users()

        review = await self._list_review.execute()
        review_count = len(review.movies)
        cache_stats = self._hls.get_cache_stats()

        last_scan = None
        if recent_scans:
            run = recent_scans[0]
            last_scan = LastScanSnapshot(
                id=str(run.id),
                started_at=run.started_at.isoformat(),
                finished_at=run.finished_at.isoformat() if run.finished_at else None,
                status=run.status.value,
            )

        return OverviewStatsOutput(
            movies_count=movies_count,
            series_count=series_count,
            users_count=users_count,
            review_count=review_count,
            last_scan=last_scan,
            hls_cache=HlsCacheSnapshot(
                size_bytes=cache_stats.size_bytes,
                max_bytes=cache_stats.max_bytes,
            ),
        )


__all__ = ["GetOverviewStatsUseCase"]
