"""DTOs for the admin Overview dashboard stats."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LastScanSnapshot:
    """The most recent scan run, for the "Last scan" card.

    Distinct from the full scan-runs list — the Overview only
    needs the headline (when it ran + how it ended), not the full
    error list.
    """

    id: str
    started_at: str
    finished_at: str | None
    status: str


@dataclass(frozen=True)
class HlsCacheSnapshot:
    """Slim HLS cache view for the Overview occupancy card.

    Drops ``last_cleared_at`` versus the dedicated System page —
    the Overview just shows the ratio.
    """

    size_bytes: int
    max_bytes: int


@dataclass(frozen=True)
class OverviewStatsOutput:
    """Aggregated counts + snapshots backing the admin Overview cards.

    Built by a single use case + single endpoint so all five
    placeholder cards on the dashboard light up together rather
    than each one flickering through its own loading state.

    Attributes:
        movies_count: Total non-deleted movies in the catalog.
        series_count: Total non-deleted series in the catalog.
        users_count: Total non-deleted users (admin + member).
        review_count: Length of the needs-enrichment-review queue.
        last_scan: Headline of the most recent scan run, or
            ``None`` when no scan has ever completed.
        hls_cache: Cache size vs configured limit.
    """

    movies_count: int
    series_count: int
    users_count: int
    review_count: int
    last_scan: LastScanSnapshot | None
    hls_cache: HlsCacheSnapshot


__all__ = ["HlsCacheSnapshot", "LastScanSnapshot", "OverviewStatsOutput"]
