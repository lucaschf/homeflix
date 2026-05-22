"""Periodic background job that locates per-season opening sequences.

Each tick:

1. Pulls a small batch of seasons whose ``intro_detection_state`` is
   ``NOT_STARTED`` or ``INSUFFICIENT_EPISODES``.
2. For each season, marks it ``IN_PROGRESS``, then in turn:
   * skips episodes that already carry a ``MANUAL`` marker (operators
     opt out of automatic detection by editing the marker manually);
   * extracts the leading audio window of every other episode and
     hands it to fpcalc;
   * runs the cross-correlation detector on the resulting
     fingerprints;
   * persists auto-detected markers whose confidence clears
     ``min_confidence``;
   * transitions the season to ``COMPLETED``,
     ``INSUFFICIENT_EPISODES``, or ``FAILED``.

A single bad season is logged and marked ``FAILED``; the rest of the
batch continues. Episodes whose audio cannot be extracted (missing
file, missing binary, unreadable codec) are quietly excluded from the
detection pool — the job is best-effort by design.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports import EpisodeFingerprint, IntroDetectorTuning
from src.modules.media.domain.value_objects import (
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.modules.media.application.ports import DetectedIntro, IntroDetectorPort
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities import Episode, Season
    from src.modules.media.domain.value_objects import EpisodeId, SeasonId
    from src.modules.media.infrastructure.audio import (
        AudioExtractor,
        ChromaprintService,
    )
    from src.modules.settings.domain.value_objects import IntroDetectionConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()

_MIN_EPISODES_FOR_DETECTION = 2
# Cap the persisted error message; matches the field-level cap on the
# Season entity but applied here too so the orchestrator never hands
# the entity an oversized payload.
_MAX_ERROR_MESSAGE_LENGTH = 2000


class IntroDetectionJob:
    """Run a single batch of audio-fingerprint intro detection.

    All operator-tunable knobs (batch size, audio window, confidence
    floor, detector tuning) are read from
    :class:`RuntimeSettings` at the start of each ``run()`` so admin
    edits propagate to the next tick without restart (ADR-013).

    Args:
        media_uow_factory: Builds fresh media UoWs. The job opens one
            UoW per state transition so a failure on a single season
            rolls back only that season's progress.
        audio_extractor: ffmpeg wrapper that produces a leading WAV
            window per episode.
        chromaprint_service: fpcalc wrapper that turns each WAV into a
            raw fingerprint.
        intro_detector: Cross-correlation algorithm that locates the
            shared intro across the season's fingerprints. Receives
            its tuning per ``detect()`` call so it stays stateless
            with respect to runtime config.
        runtime_settings: Snapshot facade for
            :class:`IntroDetectionConfig`.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        audio_extractor: AudioExtractor,
        chromaprint_service: ChromaprintService,
        intro_detector: IntroDetectorPort,
        runtime_settings: RuntimeSettings,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._audio_extractor = audio_extractor
        self._chromaprint_service = chromaprint_service
        self._intro_detector = intro_detector
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

        try:
            return await self._detect_and_persist(season, season_id, log_ctx, config)
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
            return IntroDetectionState.FAILED

    async def _detect_and_persist(
        self,
        season: Season,
        season_id: SeasonId,
        log_ctx: dict[str, str | int],
        config: IntroDetectionConfig,
    ) -> IntroDetectionState:
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
            return IntroDetectionState.INSUFFICIENT_EPISODES

        fingerprints = await self._build_fingerprints(candidates, config.audio_window_seconds)
        fingerprint_count = len(fingerprints)
        if fingerprint_count < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            _logger.info(
                "[intro-detection] season skipped: not enough usable fingerprints",
                **log_ctx,
                candidate_count=candidate_count,
                fingerprint_count=fingerprint_count,
            )
            return IntroDetectionState.INSUFFICIENT_EPISODES

        tuning = IntroDetectorTuning(
            max_hash_hamming=config.max_hash_hamming,
            tolerance_hashes=config.tolerance_hashes,
            min_intro_seconds=config.min_intro_seconds,
            max_intro_seconds=config.max_intro_seconds,
        )
        detections = await asyncio.to_thread(self._intro_detector.detect, fingerprints, tuning)
        persisted_count = await self._persist_detections(detections, config.min_confidence)
        await self._mark_state(season_id, IntroDetectionState.COMPLETED)
        _logger.info(
            "[intro-detection] season completed",
            **log_ctx,
            candidate_count=candidate_count,
            fingerprint_count=fingerprint_count,
            detected_count=len(detections),
            persisted_count=persisted_count,
        )
        return IntroDetectionState.COMPLETED

    async def _build_fingerprints(
        self,
        episodes: list[Episode],
        audio_window_seconds: int,
    ) -> list[EpisodeFingerprint]:
        """Extract audio + fingerprint each episode, dropping failures."""
        results: list[EpisodeFingerprint] = []
        for episode in episodes:
            fingerprint = await self._fingerprint_episode(episode, audio_window_seconds)
            if fingerprint is not None:
                results.append(fingerprint)
        return results

    async def _fingerprint_episode(
        self,
        episode: Episode,
        audio_window_seconds: int,
    ) -> EpisodeFingerprint | None:
        """Run ffmpeg + fpcalc against a single episode.

        Returns ``None`` when any step degrades — missing primary file,
        ffmpeg or fpcalc absent, malformed output. A ``None`` here just
        means this episode does not contribute to detection on this
        tick; nothing is persisted as failed.
        """
        if episode.id is None:
            return None
        primary = episode.primary_file
        if primary is None:
            return None
        episode_id = episode.id
        file_path = primary.file_path.value
        window = audio_window_seconds

        def _extract_and_fingerprint() -> EpisodeFingerprint | None:
            # Per the docstring: any failure here just drops the
            # episode from the detection pool. An unexpected exception
            # from the audio stack must NOT promote into a season-level
            # FAILED — the rest of the episodes might still produce a
            # quorum. Swallow + log instead of letting it bubble.
            try:
                with self._audio_extractor.extract_temporary(
                    file_path, duration_seconds=window
                ) as wav_path:
                    if wav_path is None:
                        return None
                    fingerprint = self._chromaprint_service.fingerprint(wav_path)
            except Exception:
                _logger.exception(
                    "[intro-detection] fingerprinting episode failed; skipping",
                    episode_id=str(episode_id),
                    file_path=file_path,
                )
                return None
            if fingerprint is None:
                return None
            return EpisodeFingerprint(
                episode_id=episode_id,
                hashes=list(fingerprint.hashes),
                duration_seconds=fingerprint.duration_seconds,
            )

        return await asyncio.to_thread(_extract_and_fingerprint)

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
