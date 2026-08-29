"""Adapter that runs intro detection for one season off the request path."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports import IntroDetectionRunnerPort

if TYPE_CHECKING:
    from src.infrastructure.scheduling.intro_detection_job import IntroDetectionJob
    from src.modules.media.domain.value_objects import SeasonId

_logger = get_logger()


class BackgroundIntroDetectionRunner(IntroDetectionRunnerPort):
    """Fire-and-forget wrapper around ``IntroDetectionJob.run_for_season``.

    Holds the same job instance the scheduler ticks, so a manual run
    goes through the identical pipeline (claim, detector, audit row) —
    it just skips the queue. The task is retained until it finishes so
    the event loop cannot garbage-collect a run mid-flight.

    One run per season at a time: a second request arriving while the
    first is still working reports "already running" instead of
    queueing, so an impatient double-click cannot have two workers
    fingerprint the same episodes concurrently.
    """

    def __init__(self, job: IntroDetectionJob) -> None:
        self._job = job
        self._in_flight: dict[str, asyncio.Task[None]] = {}

    def start_for_season(self, season_id: SeasonId) -> bool:
        """Launch a background run unless one is already in flight."""
        key = str(season_id)
        if key in self._in_flight:
            _logger.info(
                "[intro-detection] manual run already in flight; ignoring",
                season_id=key,
            )
            return False
        self._in_flight[key] = asyncio.create_task(self._run(season_id))
        _logger.info("[intro-detection] manual run started", season_id=key)
        return True

    async def _run(self, season_id: SeasonId) -> None:
        """Run the job, always releasing the season's in-flight slot.

        ``run_for_season`` already records ``FAILED`` plus an audit row
        for anything the detection pipeline raises; the guard here
        covers the rest (a dropped DB connection while loading the
        season) so the task never dies with an unretrieved exception.
        """
        try:
            await self._job.run_for_season(season_id)
        except Exception:
            _logger.exception(
                "[intro-detection] manual run crashed",
                season_id=str(season_id),
            )
        finally:
            self._in_flight.pop(str(season_id), None)


__all__ = ["BackgroundIntroDetectionRunner"]
