"""Periodic background job that locates per-season opening sequences.

Each tick:

1. Pulls a small batch of seasons whose ``intro_detection_state`` is
   ``NOT_STARTED`` or ``INSUFFICIENT_EPISODES``.
2. For each season, marks it ``IN_PROGRESS``, then in turn:
   * skips episodes that already carry a ``MANUAL`` marker (operators
     opt out of automatic detection by editing the marker manually);
   * hands the remaining episodes' file references to the configured
     intro detector, which owns its own analysis pipeline (audio
     fingerprinting, frame hashing, …);
   * persists detected markers whose confidence clears
     ``min_confidence``;
   * transitions the season to ``COMPLETED``,
     ``INSUFFICIENT_EPISODES``, or ``FAILED``.

A single bad season is logged and marked ``FAILED``; the rest of the
batch continues. Episodes whose media cannot be analysed (missing file,
missing binary, unreadable codec) are quietly excluded from the
detection pool by the detector — the job is best-effort by design — and
the detector reports how many episodes it actually analysed so the job
can tell "found nothing" apart from "not enough material".
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports import EpisodeMediaRef
from src.modules.media.domain.entities.intro_detection_run import (
    EpisodeDetectionResult,
    IntroDetectionRun,
)
from src.modules.media.domain.value_objects import (
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
)
from src.modules.media.infrastructure.audio import ChromaprintTuning
from src.modules.media.infrastructure.video import FrameHashTuning
from src.modules.settings.domain.value_objects import IntroDetectionAlgorithm

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.modules.media.application.ports import (
        DetectedIntro,
        IntroDetectorPort,
        IntroDetectorTuning,
    )
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities import Episode, Season
    from src.modules.media.domain.value_objects import EpisodeId, SeasonId
    from src.modules.settings.domain.value_objects import IntroDetectionConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


@dataclass
class _RunMetrics:
    """Per-season outcome + counters, used to record an audit run."""

    outcome: IntroDetectionState
    ref_count: int = 0
    analyzed_count: int = 0
    detected_count: int = 0
    persisted_count: int = 0
    episode_results: list[EpisodeDetectionResult] = field(default_factory=list)
    error: str | None = None


_logger = get_logger()

_MIN_EPISODES_FOR_DETECTION = 2
# Cap the persisted error message; matches the field-level cap on the
# Season entity but applied here too so the orchestrator never hands
# the entity an oversized payload.
_MAX_ERROR_MESSAGE_LENGTH = 2000


class IntroDetectionJob:
    """Run a single batch of intro detection.

    All operator-tunable knobs (batch size, audio window, confidence
    floor, detector tuning) are read from
    :class:`RuntimeSettings` at the start of each ``run()`` so admin
    edits propagate to the next tick without restart (ADR-013).

    Args:
        media_uow_factory: Builds fresh media UoWs. The job opens one
            UoW per state transition so a failure on a single season
            rolls back only that season's progress.
        intro_detectors: Registry of detectors keyed by algorithm. Each
            owns its own analysis pipeline and receives its tuning per
            ``detect()`` call. The active one is picked per tick from
            ``IntroDetectionConfig.algorithm`` so an admin can switch
            detectors without a restart (ADR-013).
        runtime_settings: Snapshot facade for
            :class:`IntroDetectionConfig`.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        intro_detectors: Mapping[IntroDetectionAlgorithm, IntroDetectorPort],
        runtime_settings: RuntimeSettings,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._intro_detectors = intro_detectors
        self._runtime_settings = runtime_settings

    async def run(self) -> None:
        """Process one batch of pending seasons."""
        config = await self._runtime_settings.intro_detection()
        async with self._media_uow_factory() as uow:
            seasons = list(await uow.series.find_seasons_pending_intro_detection(config.batch_size))

        if not seasons:
            return

        completed = 0
        insufficient = 0
        failed = 0
        for season in seasons:
            outcome = await self._process_season(season, config)
            if outcome == IntroDetectionState.COMPLETED:
                completed += 1
            elif outcome == IntroDetectionState.INSUFFICIENT_EPISODES:
                insufficient += 1
            elif outcome == IntroDetectionState.FAILED:
                failed += 1

        _logger.info(
            "[intro-detection] tick complete",
            seasons_completed=completed,
            seasons_insufficient=insufficient,
            seasons_failed=failed,
            batch_size=config.batch_size,
        )

    async def _process_season(
        self,
        season: Season,
        config: IntroDetectionConfig,
    ) -> IntroDetectionState:
        """Drive one season through the detection pipeline.

        Returns the state the season was transitioned to (used by
        ``run`` for the per-tick log line). The caller relies on this
        method never raising — a single bad season must not abort the
        rest of the tick.
        """
        log_ctx = _season_log_context(season)
        season_id = season.id
        if season_id is None:
            # Defensive: the repository fetches persisted seasons, so a
            # missing id would mean the entity was hand-built somewhere
            # downstream. Surface it instead of silently dropping the
            # season from the batch counters.
            _logger.error(
                "[intro-detection] skipping season with no id; cannot "
                "transition state without a primary key",
                **log_ctx,
            )
            return IntroDetectionState.FAILED

        try:
            await self._mark_state(season_id, IntroDetectionState.IN_PROGRESS)
        except Exception:
            _logger.exception(
                "[intro-detection] failed to claim season",
                **log_ctx,
            )
            return IntroDetectionState.FAILED

        started_at = datetime.now(UTC)
        try:
            metrics = await self._detect_and_persist(season, season_id, log_ctx, config)
        except Exception as exc:
            _logger.exception(
                "[intro-detection] season processing failed",
                **log_ctx,
            )
            error_message = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_MESSAGE_LENGTH]
            # Best-effort recording of the failure: if even the FAILED
            # transition itself raises (DB hiccup mid-tick), swallow it
            # so the batch loop in ``run`` can keep processing the rest
            # of the seasons.
            try:
                await self._mark_state(
                    season_id,
                    IntroDetectionState.FAILED,
                    error=error_message,
                )
            except Exception:
                _logger.exception(
                    "[intro-detection] failed to record FAILED state",
                    **log_ctx,
                )
            metrics = _RunMetrics(outcome=IntroDetectionState.FAILED, error=error_message)

        await self._record_run(season, season_id, config, metrics, started_at)
        return metrics.outcome

    async def _detect_and_persist(
        self,
        season: Season,
        season_id: SeasonId,
        log_ctx: dict[str, str | int],
        config: IntroDetectionConfig,
    ) -> _RunMetrics:
        candidates = [ep for ep in season.episodes if not _has_manual_marker(ep)]
        candidate_count = len(candidates)
        if candidate_count < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            _logger.info(
                "[intro-detection] season skipped: not enough non-MANUAL episodes",
                **log_ctx,
                total_episodes=len(season.episodes),
                candidate_count=candidate_count,
            )
            return _RunMetrics(outcome=IntroDetectionState.INSUFFICIENT_EPISODES)

        refs = _build_media_refs(candidates)
        if len(refs) < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            _logger.info(
                "[intro-detection] season skipped: not enough episodes with a primary file",
                **log_ctx,
                candidate_count=candidate_count,
                ref_count=len(refs),
            )
            return _RunMetrics(
                outcome=IntroDetectionState.INSUFFICIENT_EPISODES,
                ref_count=len(refs),
            )

        detector = self._intro_detectors.get(config.algorithm)
        if detector is None:
            # Wiring/config mismatch — surface it as a season FAILED via
            # the caller's handler rather than silently doing nothing.
            raise RuntimeError(f"no intro detector registered for algorithm {config.algorithm}")

        tuning = _build_tuning(config)
        result = await asyncio.to_thread(detector.detect, refs, tuning)

        if result.analyzed_count < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            _logger.info(
                "[intro-detection] season skipped: not enough analysable episodes",
                **log_ctx,
                ref_count=len(refs),
                analyzed_count=result.analyzed_count,
            )
            return _RunMetrics(
                outcome=IntroDetectionState.INSUFFICIENT_EPISODES,
                ref_count=len(refs),
                analyzed_count=result.analyzed_count,
            )

        episode_results = _build_episode_results(result.markers, candidates, config.min_confidence)
        persisted_count = await self._persist_detections(result.markers, config.min_confidence)
        await self._mark_state(season_id, IntroDetectionState.COMPLETED)
        _logger.info(
            "[intro-detection] season completed",
            **log_ctx,
            ref_count=len(refs),
            analyzed_count=result.analyzed_count,
            detected_count=len(result.markers),
            persisted_count=persisted_count,
        )
        return _RunMetrics(
            outcome=IntroDetectionState.COMPLETED,
            ref_count=len(refs),
            analyzed_count=result.analyzed_count,
            detected_count=len(result.markers),
            persisted_count=persisted_count,
            episode_results=episode_results,
        )

    async def _record_run(
        self,
        season: Season,
        season_id: SeasonId,
        config: IntroDetectionConfig,
        metrics: _RunMetrics,
        started_at: datetime,
    ) -> None:
        """Append an audit row for this season's run. Never raises."""
        try:
            async with self._media_uow_factory() as uow:
                # Denormalize the series title so the audit row stays
                # self-contained (survives a later rename/delete). One
                # extra lookup per recorded run — runs are infrequent.
                series = await uow.series.find_by_id(season.series_id)
                run = IntroDetectionRun(
                    series_id=str(season.series_id),
                    series_title=series.title.value if series is not None else "",
                    season_id=str(season_id),
                    season_number=season.season_number.value,
                    algorithm=config.algorithm.value,
                    outcome=metrics.outcome,
                    ref_count=metrics.ref_count,
                    analyzed_count=metrics.analyzed_count,
                    detected_count=metrics.detected_count,
                    persisted_count=metrics.persisted_count,
                    min_confidence=config.min_confidence,
                    episode_results=metrics.episode_results,
                    error=metrics.error,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                await uow.intro_detection_runs.add(run)
        except Exception:
            _logger.exception(
                "[intro-detection] failed to record audit run",
                **_season_log_context(season),
            )

    async def _persist_detections(
        self,
        detections: Mapping[EpisodeId, DetectedIntro],
        min_confidence: float,
    ) -> int:
        """Persist auto-detected markers that clear the confidence floor.

        Returns the number of markers actually written so the caller
        can include it in the per-season summary log line. Detections
        below ``min_confidence`` are silently dropped — the season is
        still flagged ``COMPLETED`` upstream so it does not get
        reprocessed indefinitely.
        """
        if not detections:
            return 0
        persisted = 0
        async with self._media_uow_factory() as uow:
            for episode_id, detected in detections.items():
                if detected.confidence < min_confidence:
                    continue
                marker = _build_auto_marker(detected)
                await uow.series.update_episode_intro(episode_id, marker)
                persisted += 1
        return persisted

    async def _mark_state(
        self,
        season_id: SeasonId,
        state: IntroDetectionState,
        *,
        error: str | None = None,
    ) -> None:
        async with self._media_uow_factory() as uow:
            await uow.series.update_season_intro_detection(
                season_id,
                state,
                attempted_at=datetime.now(UTC),
                error=error,
            )


def _build_tuning(config: IntroDetectionConfig) -> IntroDetectorTuning:
    """Build the algorithm-specific tuning for the configured detector.

    The shared bounds (intro length, analysis window) come from the top
    level; the per-algorithm knobs come from the matching sub-bucket so
    admin edits propagate without re-wiring the detector.
    """
    if config.algorithm == IntroDetectionAlgorithm.FRAME_HASH:
        return FrameHashTuning(
            min_intro_seconds=config.min_intro_seconds,
            max_intro_seconds=config.max_intro_seconds,
            analysis_window_seconds=config.analysis_window_seconds,
            hash_distance_threshold=config.frame_hash.hash_distance_threshold,
            frame_sample_fps=config.frame_hash.frame_sample_fps,
            match_tolerance_frames=config.frame_hash.match_tolerance_frames,
            max_gap_seconds=config.frame_hash.max_gap_seconds,
        )
    return ChromaprintTuning(
        min_intro_seconds=config.min_intro_seconds,
        max_intro_seconds=config.max_intro_seconds,
        analysis_window_seconds=config.analysis_window_seconds,
        max_hash_hamming=config.chromaprint.max_hash_hamming,
        tolerance_hashes=config.chromaprint.tolerance_hashes,
    )


def _build_media_refs(episodes: list[Episode]) -> list[EpisodeMediaRef]:
    """Build one media reference per episode that can actually be analysed.

    Episodes lacking an id or a primary file are dropped here — they
    cannot be keyed back to a marker, nor handed a file path, so the
    detector would never produce a usable result for them.
    """
    refs: list[EpisodeMediaRef] = []
    for episode in episodes:
        if episode.id is None:
            continue
        primary = episode.primary_file
        if primary is None:
            continue
        refs.append(EpisodeMediaRef(episode_id=episode.id, file_path=primary.file_path.value))
    return refs


def _build_episode_results(
    markers: Mapping[EpisodeId, DetectedIntro],
    candidates: list[Episode],
    min_confidence: float,
) -> list[EpisodeDetectionResult]:
    """Build the per-episode audit detail from the detector's markers.

    ``persisted`` mirrors the job's confidence floor so the audit row
    records exactly which detections were saved vs dropped — the answer
    to "detected but nothing showed up".
    """
    number_by_id = {ep.id: ep.episode_number.value for ep in candidates if ep.id is not None}
    results = [
        EpisodeDetectionResult(
            episode_id=str(episode_id),
            episode_number=number_by_id.get(episode_id, 0),
            start_seconds=detected.start_seconds,
            end_seconds=detected.end_seconds,
            confidence=detected.confidence,
            persisted=detected.confidence >= min_confidence,
        )
        for episode_id, detected in markers.items()
    ]
    results.sort(key=lambda result: result.episode_number)
    return results


def _build_auto_marker(detected: DetectedIntro) -> IntroMarker:
    """Convert a detector result into a persistable AUTO_DETECTED marker.

    Domain validation requires ``end > start``; the detector's float
    timestamps round to integer seconds for the persisted marker, and
    a 1-second floor on duration prevents the rounding from flattening
    a sub-second match into an invalid range.
    """
    start = max(0, int(detected.start_seconds))
    end = max(start + 1, int(detected.end_seconds))
    return IntroMarker(
        start_seconds=start,
        end_seconds=end,
        source=IntroMarkerSource.AUTO_DETECTED,
        confidence=detected.confidence,
    )


def _has_manual_marker(episode: Episode) -> bool:
    """Return ``True`` when the episode's intro was set manually."""
    return episode.intro is not None and episode.intro.is_manual


def _season_log_context(season: Season) -> dict[str, str | int]:
    """Build the structured log fields for a season under processing.

    ``season.series_id`` is always set (it's the parent FK), even on a
    season that somehow lacks its own external id, so the context is
    safe to compute before any guard checks.
    """
    return {
        "series_id": str(season.series_id),
        "season_id": str(season.id) if season.id is not None else "",
        "season_number": season.season_number.value,
    }


__all__ = ["IntroDetectionJob"]
