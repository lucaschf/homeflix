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
from src.modules.media.application.ports import EpisodeFingerprint
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

_logger = get_logger()

_MIN_EPISODES_FOR_DETECTION = 2
# Cap the persisted error message; matches the field-level cap on the
# Season entity but applied here too so the orchestrator never hands
# the entity an oversized payload.
_MAX_ERROR_MESSAGE_LENGTH = 2000


class IntroDetectionJob:
    """Run a single batch of audio-fingerprint intro detection.

    Args:
        media_uow_factory: Builds fresh media UoWs. The job opens one
            UoW per state transition so a failure on a single season
            rolls back only that season's progress.
        audio_extractor: ffmpeg wrapper that produces a leading WAV
            window per episode.
        chromaprint_service: fpcalc wrapper that turns each WAV into a
            raw fingerprint.
        intro_detector: Cross-correlation algorithm that locates the
            shared intro across the season's fingerprints.
        batch_size: Maximum number of seasons processed per tick.
        audio_window_seconds: How many leading seconds of each episode
            to feed into fpcalc.
        min_confidence: Auto-detected markers with confidence below
            this floor are discarded — the season is still flagged
            ``COMPLETED`` so it is not reprocessed indefinitely.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        audio_extractor: AudioExtractor,
        chromaprint_service: ChromaprintService,
        intro_detector: IntroDetectorPort,
        *,
        batch_size: int = 1,
        audio_window_seconds: int = 600,
        min_confidence: float = 0.7,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._audio_extractor = audio_extractor
        self._chromaprint_service = chromaprint_service
        self._intro_detector = intro_detector
        self._batch_size = batch_size
        self._audio_window_seconds = audio_window_seconds
        self._min_confidence = min_confidence

    async def run(self) -> None:
        """Process one batch of pending seasons."""
        async with self._media_uow_factory() as uow:
            seasons = list(await uow.series.find_seasons_pending_intro_detection(self._batch_size))

        if not seasons:
            return

        completed = 0
        insufficient = 0
        failed = 0
        for season in seasons:
            outcome = await self._process_season(season)
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
            batch_size=self._batch_size,
        )

    async def _process_season(self, season: Season) -> IntroDetectionState:
        """Drive one season through the detection pipeline.

        Returns the state the season was transitioned to (used by
        ``run`` for the per-tick log line).
        """
        season_id = season.id
        if season_id is None:
            return IntroDetectionState.FAILED

        try:
            await self._mark_state(season_id, IntroDetectionState.IN_PROGRESS)
        except Exception:
            _logger.exception(
                "[intro-detection] failed to claim season",
                season_id=str(season_id),
            )
            return IntroDetectionState.FAILED

        try:
            return await self._detect_and_persist(season, season_id)
        except Exception as exc:
            _logger.exception(
                "[intro-detection] season processing failed",
                season_id=str(season_id),
            )
            error_message = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_MESSAGE_LENGTH]
            await self._mark_state(
                season_id,
                IntroDetectionState.FAILED,
                error=error_message,
            )
            return IntroDetectionState.FAILED

    async def _detect_and_persist(self, season: Season, season_id: SeasonId) -> IntroDetectionState:
        candidates = [ep for ep in season.episodes if not _has_manual_marker(ep)]
        if len(candidates) < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            return IntroDetectionState.INSUFFICIENT_EPISODES

        fingerprints = await self._build_fingerprints(candidates)
        if len(fingerprints) < _MIN_EPISODES_FOR_DETECTION:
            await self._mark_state(season_id, IntroDetectionState.INSUFFICIENT_EPISODES)
            return IntroDetectionState.INSUFFICIENT_EPISODES

        detections = await asyncio.to_thread(self._intro_detector.detect, fingerprints)
        await self._persist_detections(detections)
        await self._mark_state(season_id, IntroDetectionState.COMPLETED)
        return IntroDetectionState.COMPLETED

    async def _build_fingerprints(self, episodes: list[Episode]) -> list[EpisodeFingerprint]:
        """Extract audio + fingerprint each episode, dropping failures."""
        results: list[EpisodeFingerprint] = []
        for episode in episodes:
            fingerprint = await self._fingerprint_episode(episode)
            if fingerprint is not None:
                results.append(fingerprint)
        return results

    async def _fingerprint_episode(self, episode: Episode) -> EpisodeFingerprint | None:
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
        window = self._audio_window_seconds

        def _extract_and_fingerprint() -> EpisodeFingerprint | None:
            with self._audio_extractor.extract_temporary(
                file_path, duration_seconds=window
            ) as wav_path:
                if wav_path is None:
                    return None
                fingerprint = self._chromaprint_service.fingerprint(wav_path)
                if fingerprint is None:
                    return None
                return EpisodeFingerprint(
                    episode_id=episode_id,
                    hashes=list(fingerprint.hashes),
                    duration_seconds=fingerprint.duration_seconds,
                )

        return await asyncio.to_thread(_extract_and_fingerprint)

    async def _persist_detections(self, detections: Mapping[EpisodeId, DetectedIntro]) -> None:
        """Persist the auto-detected markers that clear the confidence floor."""
        if not detections:
            return
        async with self._media_uow_factory() as uow:
            for episode_id, detected in detections.items():
                if detected.confidence < self._min_confidence:
                    continue
                marker = _build_auto_marker(detected)
                await uow.series.update_episode_intro(episode_id, marker)

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


__all__ = ["IntroDetectionJob"]
