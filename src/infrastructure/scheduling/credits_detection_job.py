"""Periodic background job that locates per-file end-credits onsets.

Unlike intro detection (season-scoped cross-correlation), credits
detection is per-file: each tick pulls a small batch of movies *and*
episodes whose ``credits_detection_state`` is ``NOT_STARTED``, runs the
combined detector (edge + low-motion) on each file's trailing window, and:

* persists an ``AUTO_DETECTED`` marker + ``COMPLETED`` when a candidate
  clears ``min_confidence``;
* records ``NO_CREDITS_FOUND`` when the file yields no confident onset
  (credits over moving footage, below the floor, missing file);
* records ``FAILED`` when analysis raises.

Each title is claimed ``IN_PROGRESS`` in its own UoW, analysed off the
event loop (ffmpeg decode), then finalised in a second UoW — so the slow
decode never holds a DB transaction open and one bad file never aborts
the tick. Titles already carrying a ``MANUAL`` marker are skipped.

All tunables are read from :class:`RuntimeSettings` at the start of each
``run()`` so admin edits propagate to the next tick (ADR-013).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports import CreditsDetectorTuning
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    CreditsMarkerSource,
)

if TYPE_CHECKING:
    from src.modules.media.application.ports import CreditsDetectorPort, DetectedCredits
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities import Episode, Movie
    from src.modules.media.domain.value_objects import EpisodeId, MovieId
    from src.modules.settings.domain.value_objects import CreditsDetectionConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()

_MOVIE = "movie"
_EPISODE = "episode"


class CreditsDetectionJob:
    """Run a single batch of per-file credits detection.

    Args:
        media_uow_factory: Builds fresh media UoWs. One UoW per state
            transition so a failure on a single title rolls back only
            that title's progress.
        credits_detector: The combined per-file detector behind
            :class:`CreditsDetectorPort`.
        runtime_settings: Snapshot facade for :class:`CreditsDetectionConfig`.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        credits_detector: CreditsDetectorPort,
        runtime_settings: RuntimeSettings,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._credits_detector = credits_detector
        self._runtime_settings = runtime_settings

    async def run(self) -> None:
        """Process one batch of pending movies + episodes."""
        config = await self._runtime_settings.credits_detection()
        tuning = _build_tuning(config)

        async with self._media_uow_factory() as uow:
            movies = list(await uow.movies.find_pending_credits_detection(config.batch_size))
            episodes = list(
                await uow.series.find_episodes_pending_credits_detection(config.batch_size)
            )

        if not movies and not episodes:
            return

        completed = found_none = failed = 0
        for movie in movies:
            outcome = await self._process_movie(movie, config, tuning)
            completed, found_none, failed = _tally(outcome, completed, found_none, failed)
        for episode in episodes:
            outcome = await self._process_episode(episode, config, tuning)
            completed, found_none, failed = _tally(outcome, completed, found_none, failed)

        _logger.info(
            "[credits-detection] tick complete",
            movies=len(movies),
            episodes=len(episodes),
            completed=completed,
            no_credits=found_none,
            failed=failed,
            batch_size=config.batch_size,
        )

    async def _process_movie(
        self, movie: Movie, config: CreditsDetectionConfig, tuning: CreditsDetectorTuning
    ) -> CreditsDetectionState | None:
        if movie.id is None or (movie.credits is not None and movie.credits.is_manual):
            return None
        primary = movie.primary_file
        file_path = primary.file_path.value if primary else None
        return await self._process_one(_MOVIE, movie.id, file_path, config, tuning)

    async def _process_episode(
        self, episode: Episode, config: CreditsDetectionConfig, tuning: CreditsDetectorTuning
    ) -> CreditsDetectionState | None:
        if episode.id is None or (episode.credits is not None and episode.credits.is_manual):
            return None
        primary = episode.primary_file
        file_path = primary.file_path.value if primary else None
        return await self._process_one(_EPISODE, episode.id, file_path, config, tuning)

    async def _process_one(
        self,
        kind: str,
        media_id: MovieId | EpisodeId,
        file_path: str | None,
        config: CreditsDetectionConfig,
        tuning: CreditsDetectorTuning,
    ) -> CreditsDetectionState:
        """Claim, detect, and finalise a single title. Never raises."""
        try:
            await self._set(kind, media_id, None, CreditsDetectionState.IN_PROGRESS)
            result: DetectedCredits | None = None
            if file_path:
                result = await asyncio.to_thread(self._credits_detector.detect, file_path, tuning)
            if result is not None and result.confidence >= config.min_confidence:
                await self._set(
                    kind, media_id, _build_auto_marker(result), CreditsDetectionState.COMPLETED
                )
                return CreditsDetectionState.COMPLETED
            await self._set(kind, media_id, None, CreditsDetectionState.NO_CREDITS_FOUND)
            return CreditsDetectionState.NO_CREDITS_FOUND
        except Exception:
            _logger.exception(
                "[credits-detection] processing failed", kind=kind, media_id=str(media_id)
            )
            try:
                await self._set(kind, media_id, None, CreditsDetectionState.FAILED)
            except Exception:
                _logger.exception(
                    "[credits-detection] failed to record FAILED state",
                    kind=kind,
                    media_id=str(media_id),
                )
            return CreditsDetectionState.FAILED

    async def _set(
        self,
        kind: str,
        media_id: MovieId | EpisodeId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> None:
        async with self._media_uow_factory() as uow:
            if kind == _MOVIE:
                await uow.movies.update_movie_credits(media_id, marker, state)  # type: ignore[arg-type]
            else:
                await uow.series.update_episode_credits(media_id, marker, state)  # type: ignore[arg-type]


def _build_tuning(config: CreditsDetectionConfig) -> CreditsDetectorTuning:
    """Map the persisted config bucket onto the detector's tuning."""
    return CreditsDetectorTuning(
        analysis_window_seconds=config.analysis_window_seconds,
        frame_sample_fps=config.frame_sample_fps,
        min_credits_seconds=config.min_credits_seconds,
        edge_rel_factor=config.edge_rel_factor,
        motion_rel_factor=config.motion_rel_factor,
    )


def _build_auto_marker(detected: DetectedCredits) -> CreditsMarker:
    """Convert a detector result into a persistable AUTO_DETECTED marker."""
    return CreditsMarker(
        start_seconds=max(0, int(detected.start_seconds)),
        source=CreditsMarkerSource.AUTO_DETECTED,
        confidence=detected.confidence,
    )


def _tally(
    outcome: CreditsDetectionState | None, completed: int, found_none: int, failed: int
) -> tuple[int, int, int]:
    """Fold one title's outcome into the per-tick counters."""
    if outcome == CreditsDetectionState.COMPLETED:
        return completed + 1, found_none, failed
    if outcome == CreditsDetectionState.NO_CREDITS_FOUND:
        return completed, found_none + 1, failed
    if outcome == CreditsDetectionState.FAILED:
        return completed, found_none, failed + 1
    return completed, found_none, failed


__all__ = ["CreditsDetectionJob"]
