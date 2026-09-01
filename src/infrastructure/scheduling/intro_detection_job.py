"""Periodic background job that locates per-season opening sequences.

Each tick:

1. Pulls a small batch of seasons whose ``intro_detection_state`` is
   ``NOT_STARTED`` or ``INSUFFICIENT_EPISODES``.
2. For each season, marks it ``IN_PROGRESS``, then in turn:
   * skips episodes a human already settled — a ``MANUAL`` marker, or
     a confirmation that the episode has no intro at all;
   * hands the remaining episodes' file references to the configured
     intro detector, which owns its own analysis pipeline (audio
     fingerprinting, frame hashing, …);
   * persists detected markers whose confidence clears
     ``min_confidence``;
   * retries with ``fallback_algorithm`` when the primary detector
     persisted nothing at all — the two detectors are blind to
     different material, so the second pass recovers seasons the first
     cannot see;
   * transitions the season to ``COMPLETED``,
     ``INSUFFICIENT_EPISODES``, or ``FAILED``.

Every detector attempt records its own audit row, so a season that
needed the fallback shows both passes and what each one found.

A single bad season is logged and marked ``FAILED``; the rest of the
batch continues. Episodes whose media cannot be analysed (missing file,
missing binary, unreadable codec) are quietly excluded from the
detection pool by the detector — the job is best-effort by design — and
the detector reports how many episodes it actually analysed so the job
can tell "found nothing" apart from "not enough material".

``run_for_season`` is the operator-triggered entry point: it drives one
named season through the same pipeline right away, without waiting for
the next tick or competing with the batch for a queue slot.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports import EpisodeMediaRef, IntroDetectionProgress
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
    from src.modules.media.domain.value_objects import EpisodeId, SeasonId, SeriesId
    from src.modules.settings.domain.value_objects import IntroDetectionConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


@dataclass
class _RunMetrics:
    """Outcome + counters for one detector attempt.

    Maps one-to-one onto an :class:`IntroDetectionRun` audit row, so a
    season retried with the fallback detector records one of these per
    attempt rather than collapsing both into a single row.
    """

    algorithm: IntroDetectionAlgorithm
    outcome: IntroDetectionState
    started_at: datetime
    finished_at: datetime
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
        stale_before = datetime.now(UTC) - timedelta(minutes=config.stale_claim_timeout_minutes)
        async with self._media_uow_factory() as uow:
            seasons = list(
                await uow.series.find_seasons_pending_intro_detection(
                    config.batch_size, stale_before=stale_before
                )
            )

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

    async def run_for_season(self, season_id: SeasonId) -> IntroDetectionState:
        """Process one named season now, bypassing the pending queue.

        Backs the admin "detect now" action: the season is driven
        through the exact same pipeline a tick would use (same claim,
        same detector, same audit row), so the result is
        indistinguishable from a scheduled run apart from its timing.
        Eligibility is not re-checked here — the caller asked for this
        season explicitly.

        Args:
            season_id: External id of the season to process.

        Returns:
            The state the season was transitioned to, or ``FAILED`` when
            the season no longer exists.
        """
        config = await self._runtime_settings.intro_detection()
        async with self._media_uow_factory() as uow:
            season = await uow.series.find_season_for_intro_detection(season_id)

        if season is None:
            _logger.warning(
                "[intro-detection] season vanished before its manual run",
                season_id=str(season_id),
            )
            return IntroDetectionState.FAILED

        return await self._process_season(season, config)

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
        series_title = await self._resolve_series_title(season.series_id)
        log_ctx = _season_log_context(season, series_title)
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

        # Emit up front so operators can see which series/season is being
        # worked on *while* the (slow) detection runs, not only once it
        # finishes.
        _logger.info("[intro-detection] season started", **log_ctx)

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
            attempts = await self._detect_and_persist(
                season, season_id, log_ctx, config, started_at
            )
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
            attempts = [
                _RunMetrics(
                    algorithm=config.algorithm,
                    outcome=IntroDetectionState.FAILED,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error=error_message,
                )
            ]

        for attempt in attempts:
            await self._record_run(season, season_id, config, attempt, series_title)
        return attempts[-1].outcome

    async def _detect_and_persist(
        self,
        season: Season,
        season_id: SeasonId,
        log_ctx: dict[str, str | int],
        config: IntroDetectionConfig,
        started_at: datetime,
    ) -> list[_RunMetrics]:
        """Drive the season through the configured detector chain.

        Returns one entry per detector attempt — the caller records an
        audit row for each. The chain stops as soon as an attempt
        persists a marker, and the season's final state comes from the
        last attempt made.
        """
        episode_count = len(season.episodes)
        candidates = [ep for ep in season.episodes if not _is_operator_settled(ep)]
        candidate_count = len(candidates)
        if candidate_count < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(
                season_id,
                IntroDetectionState.INSUFFICIENT_EPISODES,
                attempted_episode_count=episode_count,
            )
            _logger.info(
                "[intro-detection] season skipped: not enough undecided episodes",
                **log_ctx,
                total_episodes=len(season.episodes),
                candidate_count=candidate_count,
            )
            return [
                _RunMetrics(
                    algorithm=config.algorithm,
                    outcome=IntroDetectionState.INSUFFICIENT_EPISODES,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            ]

        refs = _build_media_refs(candidates)
        if len(refs) < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(
                season_id,
                IntroDetectionState.INSUFFICIENT_EPISODES,
                attempted_episode_count=episode_count,
            )
            _logger.info(
                "[intro-detection] season skipped: not enough episodes with a primary file",
                **log_ctx,
                candidate_count=candidate_count,
                ref_count=len(refs),
            )
            return [
                _RunMetrics(
                    algorithm=config.algorithm,
                    outcome=IntroDetectionState.INSUFFICIENT_EPISODES,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    ref_count=len(refs),
                )
            ]

        episode_numbers = _episode_numbers_by_id(candidates)
        attempts: list[_RunMetrics] = []
        for algorithm, detector in self._detector_chain(config, log_ctx):
            attempt = await self._attempt_detection(
                algorithm, detector, refs, episode_numbers, log_ctx, config
            )
            attempts.append(attempt)
            if attempt.persisted_count > 0:
                break
            _logger.info(
                "[intro-detection] detector persisted no marker",
                **log_ctx,
                algorithm=algorithm.value,
            )

        await self._mark_state(
            season_id,
            attempts[-1].outcome,
            attempted_episode_count=episode_count,
        )
        return attempts

    def _detector_chain(
        self,
        config: IntroDetectionConfig,
        log_ctx: dict[str, str | int],
    ) -> list[tuple[IntroDetectionAlgorithm, IntroDetectorPort]]:
        """Resolve the primary detector followed by its fallback.

        A missing primary is a wiring/config mismatch and is surfaced as
        a season FAILED via the caller's handler rather than silently
        doing nothing. A missing fallback only costs the retry, so it is
        logged and dropped instead of sinking a season the primary can
        still handle on its own.
        """
        primary = self._intro_detectors.get(config.algorithm)
        if primary is None:
            raise RuntimeError(f"no intro detector registered for algorithm {config.algorithm}")
        chain = [(config.algorithm, primary)]

        fallback = config.fallback_algorithm
        if fallback is None or fallback == config.algorithm:
            return chain

        fallback_detector = self._intro_detectors.get(fallback)
        if fallback_detector is None:
            _logger.warning(
                "[intro-detection] configured fallback detector is not registered; skipping",
                **log_ctx,
                fallback_algorithm=fallback.value,
            )
            return chain

        chain.append((fallback, fallback_detector))
        return chain

    async def _attempt_detection(
        self,
        algorithm: IntroDetectionAlgorithm,
        detector: IntroDetectorPort,
        refs: list[EpisodeMediaRef],
        episode_numbers: Mapping[EpisodeId, int],
        log_ctx: dict[str, str | int],
        config: IntroDetectionConfig,
    ) -> _RunMetrics:
        """Run one detector over the season and persist what it found.

        Deliberately does not transition the season: in a fallback chain
        only the last attempt gets to decide the state, so that call
        belongs to the caller.
        """
        started_at = datetime.now(UTC)
        tuning = _build_tuning(algorithm, config)
        _logger.info(
            "[intro-detection] analysing episodes",
            **log_ctx,
            episode_count=len(refs),
            algorithm=algorithm.value,
            analysis_window_seconds=config.analysis_window_seconds,
        )
        result = await asyncio.to_thread(
            detector.detect,
            refs,
            tuning,
            _build_progress_logger(log_ctx, episode_numbers),
        )

        if result.analyzed_count < _MIN_EPISODES_FOR_DETECTION:
            _logger.info(
                "[intro-detection] not enough analysable episodes",
                **log_ctx,
                algorithm=algorithm.value,
                ref_count=len(refs),
                analyzed_count=result.analyzed_count,
            )
            return _RunMetrics(
                algorithm=algorithm,
                outcome=IntroDetectionState.INSUFFICIENT_EPISODES,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                ref_count=len(refs),
                analyzed_count=result.analyzed_count,
            )

        episode_results = _build_episode_results(
            result.markers, episode_numbers, config.min_confidence
        )
        persisted_count = await self._persist_detections(result.markers, config.min_confidence)
        _logger.info(
            "[intro-detection] detector finished",
            **log_ctx,
            algorithm=algorithm.value,
            ref_count=len(refs),
            analyzed_count=result.analyzed_count,
            detected_count=len(result.markers),
            persisted_count=persisted_count,
        )
        return _RunMetrics(
            algorithm=algorithm,
            outcome=IntroDetectionState.COMPLETED,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            ref_count=len(refs),
            analyzed_count=result.analyzed_count,
            detected_count=len(result.markers),
            persisted_count=persisted_count,
            episode_results=episode_results,
        )

    async def _resolve_series_title(self, series_id: SeriesId) -> str:
        """Best-effort fetch of the parent series title for log + audit.

        Returns an empty string when the series can't be resolved (a
        mid-tick delete, say) — never raises, so a lookup hiccup can't
        abort the season's processing.
        """
        try:
            async with self._media_uow_factory() as uow:
                series = await uow.series.find_by_id(series_id)
        except Exception:
            _logger.exception("[intro-detection] failed to resolve series title")
            return ""
        return series.title.value if series is not None else ""

    async def _record_run(
        self,
        season: Season,
        season_id: SeasonId,
        config: IntroDetectionConfig,
        metrics: _RunMetrics,
        series_title: str,
    ) -> None:
        """Append an audit row for one detector attempt. Never raises.

        ``series_title`` is resolved once by the caller and threaded in so
        the audit row stays self-contained (survives a later rename/delete)
        without a second lookup.
        """
        try:
            async with self._media_uow_factory() as uow:
                run = IntroDetectionRun(
                    series_id=str(season.series_id),
                    series_title=series_title,
                    season_id=str(season_id),
                    season_number=season.season_number.value,
                    algorithm=metrics.algorithm.value,
                    outcome=metrics.outcome,
                    ref_count=metrics.ref_count,
                    analyzed_count=metrics.analyzed_count,
                    detected_count=metrics.detected_count,
                    persisted_count=metrics.persisted_count,
                    min_confidence=config.min_confidence,
                    episode_results=metrics.episode_results,
                    error=metrics.error,
                    started_at=metrics.started_at,
                    finished_at=metrics.finished_at,
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
        attempted_episode_count: int | None = None,
        error: str | None = None,
    ) -> None:
        async with self._media_uow_factory() as uow:
            await uow.series.update_season_intro_detection(
                season_id,
                state,
                attempted_at=datetime.now(UTC),
                attempted_episode_count=attempted_episode_count,
                error=error,
            )


def _build_tuning(
    algorithm: IntroDetectionAlgorithm,
    config: IntroDetectionConfig,
) -> IntroDetectorTuning:
    """Build the tuning for ``algorithm``.

    The shared bounds (intro length, analysis window) come from the top
    level; the per-algorithm knobs come from the matching sub-bucket so
    admin edits propagate without re-wiring the detector. Keyed off the
    algorithm being attempted rather than the configured primary, so a
    fallback attempt gets its own calibration.
    """
    if algorithm == IntroDetectionAlgorithm.FRAME_HASH:
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


def _episode_numbers_by_id(episodes: list[Episode]) -> dict[EpisodeId, int]:
    """Map each episode's id to its number, for log + audit labelling."""
    return {ep.id: ep.episode_number.value for ep in episodes if ep.id is not None}


def _build_progress_logger(
    log_ctx: dict[str, str | int],
    episode_numbers: Mapping[EpisodeId, int],
) -> IntroDetectionProgress:
    """Build the per-episode progress callback handed to the detector.

    Detection is minutes-long and silent by nature; this turns it into
    one line per episode so an operator can watch a run advance instead
    of guessing whether it wedged. Emitted through structlog on purpose:
    the detectors' own stdlib loggers have no handler configured, so
    anything below WARNING there is discarded.

    Runs on the detector's worker thread — keep it to logging.
    """

    def _log(done: int, total: int, episode_id: EpisodeId) -> None:
        _logger.info(
            "[intro-detection] episode analysed",
            **log_ctx,
            episode_number=episode_numbers.get(episode_id, 0),
            progress=f"{done}/{total}",
        )

    return _log


def _build_episode_results(
    markers: Mapping[EpisodeId, DetectedIntro],
    episode_numbers: Mapping[EpisodeId, int],
    min_confidence: float,
) -> list[EpisodeDetectionResult]:
    """Build the per-episode audit detail from the detector's markers.

    ``persisted`` mirrors the job's confidence floor so the audit row
    records exactly which detections were saved vs dropped — the answer
    to "detected but nothing showed up".
    """
    results = [
        EpisodeDetectionResult(
            episode_id=str(episode_id),
            episode_number=episode_numbers.get(episode_id, 0),
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


def _is_operator_settled(episode: Episode) -> bool:
    """Return ``True`` when a human already settled this episode's intro.

    Covers both deliberate verdicts: a ``MANUAL`` marker, and a
    confirmation that the episode has no opening sequence at all.
    Re-running detection over either would silently overwrite the
    operator's decision on the next tick.
    """
    if episode.intro_absent_at is not None:
        return True
    return episode.intro is not None and episode.intro.is_manual


def _season_log_context(season: Season, series_title: str = "") -> dict[str, str | int]:
    """Build the structured log fields for a season under processing.

    ``season.series_id`` is always set (it's the parent FK), even on a
    season that somehow lacks its own external id, so the context is
    safe to compute before any guard checks. ``series_title`` is included
    when resolved so log lines read as "Show — Season 2" rather than bare
    ids; it defaults to empty for call sites that log before resolving it.
    """
    ctx: dict[str, str | int] = {
        "series_id": str(season.series_id),
        "season_id": str(season.id) if season.id is not None else "",
        "season_number": season.season_number.value,
    }
    if series_title:
        ctx["series_title"] = series_title
    return ctx


__all__ = ["IntroDetectionJob"]
