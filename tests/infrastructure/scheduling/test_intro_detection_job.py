"""Tests for IntroDetectionJob.

Mocks the media UoW factory and the three audio services so the
tests exercise orchestration (state transitions, episode filtering,
confidence floor, error handling) without touching ffmpeg, fpcalc, or
the database.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.intro_detection_job import IntroDetectionJob
from src.modules.media.application.ports import DetectedIntro
from src.modules.media.domain.entities import Episode, Season
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    EpisodeNumber,
    FilePath,
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
    MediaFile,
    Resolution,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
)
from src.modules.media.infrastructure.audio import ChromaprintFingerprint

if TYPE_CHECKING:
    from collections.abc import Iterator


def _make_episode(
    *,
    series_id: SeriesId,
    episode_number: int = 1,
    file_path: str | None = None,
    intro: IntroMarker | None = None,
) -> Episode:
    path = file_path or f"/series/show/s01e{episode_number:02d}.mkv"
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(episode_number),
        title=Title(f"Episode {episode_number}"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(path),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    if intro is not None:
        episode = episode.with_intro_marker(intro)
    return episode


def _make_season(*, episodes: list[Episode], series_id: SeriesId) -> Season:
    return Season(
        id=SeasonId.generate(),
        series_id=series_id,
        season_number=SeasonNumber(1),
        title=Title("Season 1"),
        episodes=episodes,
    )


def _build_uow(*, pending_seasons: list[Season]) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.series = AsyncMock()
    uow.series.find_seasons_pending_intro_detection = AsyncMock(return_value=pending_seasons)
    uow.series.update_season_intro_detection = AsyncMock(return_value=True)
    uow.series.update_episode_intro = AsyncMock(return_value=True)
    return uow


def _make_audio_extractor(*, returns: list[Path | None] | None = None) -> MagicMock:
    """Return a stub AudioExtractor whose ``extract_temporary`` yields paths.

    ``returns`` is consumed in order — one path per call. A single
    ``None`` triggers the "extraction failed" branch in the job.
    """
    queue: list[Path | None] = list(returns) if returns is not None else []
    extractor = MagicMock()

    @contextmanager
    def extract_temporary(_file_path: str, *, duration_seconds: int) -> Iterator[Path | None]:
        del duration_seconds
        if queue:
            yield queue.pop(0)
        else:
            yield Path("/tmp/fake.wav")

    extractor.extract_temporary.side_effect = extract_temporary
    return extractor


def _make_chromaprint(*, returns: list[ChromaprintFingerprint | None] | None = None) -> MagicMock:
    queue: list[ChromaprintFingerprint | None] = list(returns) if returns is not None else []
    service = MagicMock()

    def fingerprint(_path: object) -> ChromaprintFingerprint | None:
        if queue:
            return queue.pop(0)
        return ChromaprintFingerprint(duration_seconds=300.0, hashes=[1, 2, 3])

    service.fingerprint.side_effect = fingerprint
    return service


def _make_detector(*, detections: dict[EpisodeId, DetectedIntro]) -> MagicMock:
    detector = MagicMock()
    detector.detect.return_value = detections
    return detector


@pytest.mark.unit
class TestIntroDetectionJob:
    """Orchestration tests for IntroDetectionJob.run."""

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_pending_seasons(self) -> None:
        uow = _build_uow(pending_seasons=[])
        factory = MagicMock(return_value=uow)
        detector = _make_detector(detections={})

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=detector,
        )
        await job.run()

        detector.detect.assert_not_called()
        uow.series.update_season_intro_detection.assert_not_awaited()
        uow.series.update_episode_intro.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_persists_high_confidence_detections_and_marks_completed(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2, 3)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        detections = {
            ep.id: DetectedIntro(
                start_seconds=10.0,
                end_seconds=80.0,
                confidence=0.9,
            )
            for ep in episodes
            if ep.id is not None
        }
        detector = _make_detector(detections=detections)

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=detector,
            min_confidence=0.7,
        )
        await job.run()

        assert uow.series.update_episode_intro.await_count == 3
        for call_args in uow.series.update_episode_intro.await_args_list:
            persisted = call_args.args[1]
            assert isinstance(persisted, IntroMarker)
            assert persisted.source == IntroMarkerSource.AUTO_DETECTED
            assert persisted.confidence == pytest.approx(0.9)
        # IN_PROGRESS then COMPLETED.
        states_used = [
            call.args[1] for call in uow.series.update_season_intro_detection.await_args_list
        ]
        assert states_used == [
            IntroDetectionState.IN_PROGRESS,
            IntroDetectionState.COMPLETED,
        ]

    @pytest.mark.asyncio
    async def test_skips_low_confidence_detections_but_still_completes(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        detections = {
            ep.id: DetectedIntro(start_seconds=0.0, end_seconds=60.0, confidence=0.4)
            for ep in episodes
            if ep.id is not None
        }
        detector = _make_detector(detections=detections)

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=detector,
            min_confidence=0.7,
        )
        await job.run()

        # Below the floor — no markers persisted.
        uow.series.update_episode_intro.assert_not_awaited()
        # Season still flagged as completed so it isn't reprocessed.
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.COMPLETED

    @pytest.mark.asyncio
    async def test_filters_episodes_with_manual_markers_from_detection_pool(
        self,
    ) -> None:
        sid = SeriesId.generate()
        manual_marker = IntroMarker(
            start_seconds=5,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )
        # Two of three episodes carry a MANUAL marker → only one
        # auto-detection candidate left, which is below the
        # 2-episode floor.
        episodes = [
            _make_episode(series_id=sid, episode_number=1, intro=manual_marker),
            _make_episode(series_id=sid, episode_number=2, intro=manual_marker),
            _make_episode(series_id=sid, episode_number=3),
        ]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        detector = _make_detector(detections={})

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=detector,
        )
        await job.run()

        detector.detect.assert_not_called()
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.INSUFFICIENT_EPISODES

    @pytest.mark.asyncio
    async def test_drops_to_insufficient_when_extraction_fails_for_most(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2, 3)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        # Two of three extractions fail (None) — only one usable
        # fingerprint, which is below the 2-episode floor.
        extractor = _make_audio_extractor(returns=[None, None, Path("/tmp/fake.wav")])
        detector = _make_detector(detections={})

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=extractor,
            chromaprint_service=_make_chromaprint(),
            intro_detector=detector,
        )
        await job.run()

        detector.detect.assert_not_called()
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.INSUFFICIENT_EPISODES

    @pytest.mark.asyncio
    async def test_marks_failed_when_detector_raises(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)

        broken_detector = MagicMock()
        broken_detector.detect.side_effect = RuntimeError("kaboom")

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=broken_detector,
        )
        await job.run()

        # IN_PROGRESS then FAILED with a captured error message.
        calls = uow.series.update_season_intro_detection.await_args_list
        assert calls[0].args[1] == IntroDetectionState.IN_PROGRESS
        terminal_call = calls[-1]
        assert terminal_call.args[1] == IntroDetectionState.FAILED
        assert "kaboom" in terminal_call.kwargs["error"]
        uow.series.update_episode_intro.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_episodes_whose_fingerprint_fails(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2, 3)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        # The middle episode's fingerprint fails — the detector still
        # gets the other two and produces a result.
        chromaprint = _make_chromaprint(
            returns=[
                ChromaprintFingerprint(duration_seconds=300.0, hashes=[1, 2, 3]),
                None,
                ChromaprintFingerprint(duration_seconds=300.0, hashes=[1, 2, 3]),
            ]
        )
        detector = _make_detector(detections={})

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=chromaprint,
            intro_detector=detector,
        )
        await job.run()

        # Detector saw two fingerprints, one was dropped.
        passed_to_detector = detector.detect.call_args.args[0]
        assert len(passed_to_detector) == 2
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.COMPLETED

    @pytest.mark.asyncio
    async def test_respects_batch_size(self) -> None:
        sid = SeriesId.generate()
        seasons = [
            _make_season(
                episodes=[
                    _make_episode(
                        series_id=sid,
                        episode_number=i,
                        file_path=f"/series/show/s0{n}e{i:02d}.mkv",
                    )
                    for i in (1, 2)
                ],
                series_id=sid,
            )
            for n in range(3)
        ]
        # Even though 3 are pending, the batch_size=1 contract means
        # find_seasons_pending_intro_detection is called with limit=1
        # and only the first is processed.
        uow = _build_uow(pending_seasons=seasons[:1])
        factory = MagicMock(return_value=uow)

        job = IntroDetectionJob(
            media_uow_factory=factory,
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            intro_detector=_make_detector(detections={}),
            batch_size=1,
        )
        await job.run()

        called_with = uow.series.find_seasons_pending_intro_detection.await_args
        assert called_with.args[0] == 1
