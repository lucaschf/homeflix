"""Periodic background job that re-runs the catalog-wide dedup sweep.

Each tick reads the current ``scan_dedup`` runtime settings and, when
the sweep is still enabled, invokes
:class:`SweepMovieConflictsUseCase`. The job is intentionally a thin
adapter — all aggregation and error handling lives in the use case.

ADR-015 Phase 6.5.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config.logging import get_logger

if TYPE_CHECKING:
    from src.modules.media.application.use_cases.sweep_movie_conflicts import (
        SweepMovieConflictsUseCase,
    )
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()


class ScanDedupSweepJob:
    """One periodic scan-dedup sweep, gated on the current runtime setting.

    The job is registered once at startup with the configured interval;
    on every tick it re-reads ``scan_dedup`` so an operator toggling the
    sweep off mid-day stops new passes from running without waiting for
    a restart. (The interval itself only takes effect on the next
    startup — APScheduler doesn't live-rescheduled registered jobs.)

    Args:
        sweep_use_case: The catalog-wide sweep.
        runtime_settings: Snapshot facade for
            :class:`ScanDedupConfig` — read fresh each tick.
    """

    def __init__(
        self,
        sweep_use_case: SweepMovieConflictsUseCase,
        runtime_settings: RuntimeSettings,
    ) -> None:
        self._sweep_use_case = sweep_use_case
        self._runtime_settings = runtime_settings

    async def run(self) -> None:
        """Execute one sweep pass when the runtime config still enables it."""
        config = await self._runtime_settings.scan_dedup()
        if not config.sweep_enabled:
            _logger.debug("[scan-dedup-sweep] disabled at tick; skipping")
            return

        result = await self._sweep_use_case.execute()
        _logger.info(
            "[scan-dedup-sweep] tick complete",
            movies_scanned=result.movies_scanned,
            conflicts_created=result.conflicts_created,
        )


__all__ = ["ScanDedupSweepJob"]
