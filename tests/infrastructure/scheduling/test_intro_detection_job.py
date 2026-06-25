"""Tests for IntroDetectionJob.

Mocks the media UoW factory and the intro detector so the tests
exercise orchestration (state transitions, episode filtering,
confidence floor, error handling) without touching ffmpeg, fpcalc, or
the database. The detector owns its own analysis pipeline now, so the
job only sees its :class:`IntroDetectionResult`.
"""

from __future__ import annotations

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.intro_detection_job import IntroDetectionJob
from src.modules.media.application.ports import (
    DetectedIntro,
    IntroDetectionResult,
)
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
from src.modules.settings.domain.value_objects import (
    IntroDetectionAlgorithm,
    IntroDetectionConfig,
)


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
    # The audit-run recorder looks up the series to denormalize its
    # title; return a stub whose ``title.value`` is a real string.
    uow.series.find_by_id = AsyncMock(
        return_value=SimpleNamespace(title=SimpleNamespace(value="Test Series"))
    )
    return uow


def _make_detector(*, result: IntroDetectionResult | None = None) -> MagicMock:
    detector = MagicMock()
    detector.detect.return_value = result or IntroDetectionResult(markers={}, analyzed_count=0)
    return detector


def _registry(detector: MagicMock) -> dict[IntroDetectionAlgorithm, MagicMock]:
    """Map a single detector under every algorithm.

    The default :class:`IntroDetectionConfig` selects ``FRAME_HASH``;
    mapping the same mock under both keys keeps the orchestration tests
    agnostic to which algorithm is active.
    """
    return {
        IntroDetectionAlgorithm.CHROMAPRINT: detector,
        IntroDetectionAlgorithm.FRAME_HASH: detector,
    }


def _make_runtime_settings(*, intro: IntroDetectionConfig | None = None) -> AsyncMock:
    """Return a fake :class:`RuntimeSettings` exposing ``intro_detection``."""
    runtime = AsyncMock()
    runtime.intro_detection = AsyncMock(return_value=intro or IntroDetectionConfig())
    return runtime


@pytest.mark.unit
class TestIntroDetectionJob:
    """Orchestration tests for IntroDetectionJob.run."""

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_pending_seasons(self) -> None:
        uow = _build_uow(pending_seasons=[])
        factory = MagicMock(return_value=uow)
        detector = _make_detector()

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
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
        markers = {
            ep.id: DetectedIntro(start_seconds=10.0, end_seconds=80.0, confidence=0.9)
            for ep in episodes
            if ep.id is not None
        }
        detector = _make_detector(result=IntroDetectionResult(markers=markers, analyzed_count=3))

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
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
    async def test_passes_episode_refs_to_the_detector(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        detector = _make_detector(result=IntroDetectionResult(markers={}, analyzed_count=2))

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        refs = detector.detect.call_args.args[0]
        assert {ref.episode_id for ref in refs} == {ep.id for ep in episodes}
        assert all(ref.file_path.endswith(".mkv") for ref in refs)

    @pytest.mark.asyncio
    async def test_skips_low_confidence_detections_but_still_completes(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        markers = {
            ep.id: DetectedIntro(start_seconds=0.0, end_seconds=60.0, confidence=0.4)
            for ep in episodes
            if ep.id is not None
        }
        detector = _make_detector(result=IntroDetectionResult(markers=markers, analyzed_count=2))

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        # Below the floor — no markers persisted.
        uow.series.update_episode_intro.assert_not_awaited()
        # Season still flagged as completed so it isn't reprocessed.
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.COMPLETED

    @pytest.mark.asyncio
    async def test_filters_episodes_with_manual_markers_from_detection_pool(self) -> None:
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
        detector = _make_detector()

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        detector.detect.assert_not_called()
        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.INSUFFICIENT_EPISODES

    @pytest.mark.asyncio
    async def test_drops_to_insufficient_when_detector_analyzes_too_few(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2, 3)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        # The detector could only analyse one episode (the rest had
        # unreadable media) — below the 2-episode floor.
        detector = _make_detector(result=IntroDetectionResult(markers={}, analyzed_count=1))

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        uow.series.update_episode_intro.assert_not_awaited()
        terminal_call = uow.series.update_season_intro_detection.await_args_list[-1]
        assert terminal_call.args[1] == IntroDetectionState.INSUFFICIENT_EPISODES
        # The episode count is stamped so the season is only re-armed once
        # more episodes land, instead of being retried every tick.
        assert terminal_call.kwargs["attempted_episode_count"] == 3

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
            intro_detectors=_registry(broken_detector),
            runtime_settings=_make_runtime_settings(),
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
    async def test_does_not_abort_batch_when_failed_state_recording_raises(self) -> None:
        # If the FAILED transition itself raises (e.g. DB hiccup mid-tick)
        # the batch loop must continue to the next season rather than
        # aborting silently.
        sid = SeriesId.generate()
        eps_a = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season_a = _make_season(episodes=eps_a, series_id=sid)
        eps_b = [
            _make_episode(series_id=sid, episode_number=i, file_path=f"/series/s02e{i:02d}.mkv")
            for i in (1, 2)
        ]
        season_b = _make_season(episodes=eps_b, series_id=sid)

        # update_season_intro_detection raises on the second call
        # (which is the FAILED transition for season_a after the
        # detector raised). Subsequent calls succeed so season_b can
        # complete.
        uow = AsyncMock()
        uow.__aenter__.return_value = uow
        uow.__aexit__.return_value = None
        uow.series = AsyncMock()
        uow.series.find_seasons_pending_intro_detection = AsyncMock(
            return_value=[season_a, season_b]
        )
        update_outcomes: list[bool | Exception] = [
            True,  # season_a IN_PROGRESS → ok
            RuntimeError("db hiccup"),  # season_a FAILED → boom
            True,  # season_b IN_PROGRESS → ok
            True,  # season_b COMPLETED → ok
        ]

        async def update_state(*_args: object, **_kwargs: object) -> bool:
            outcome = update_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        uow.series.update_season_intro_detection.side_effect = update_state
        uow.series.update_episode_intro = AsyncMock(return_value=True)
        factory = MagicMock(return_value=uow)

        broken_detector = MagicMock()
        # First call (season_a) raises; second call (season_b) returns an
        # empty result with enough analysed episodes so it completes.
        broken_detector.detect.side_effect = [
            RuntimeError("kaboom"),
            IntroDetectionResult(markers={}, analyzed_count=2),
        ]

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(broken_detector),
            runtime_settings=_make_runtime_settings(),
        )
        # Must not raise — the batch loop survives the failed
        # state-recording on season_a.
        await job.run()

        # Both seasons walked the IN_PROGRESS path; season_b reached
        # COMPLETED despite season_a's recording failure.
        states_used = [
            call.args[1] for call in uow.series.update_season_intro_detection.await_args_list
        ]
        assert states_used == [
            IntroDetectionState.IN_PROGRESS,
            IntroDetectionState.FAILED,
            IntroDetectionState.IN_PROGRESS,
            IntroDetectionState.COMPLETED,
        ]

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
            intro_detectors=_registry(
                _make_detector(result=IntroDetectionResult(markers={}, analyzed_count=2))
            ),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        called_with = uow.series.find_seasons_pending_intro_detection.await_args
        assert called_with.args[0] == 1
        # A stale-claim cutoff is passed so orphaned IN_PROGRESS seasons
        # become reclaimable instead of stuck forever.
        assert isinstance(called_with.kwargs["stale_before"], datetime)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "algorithm",
        [IntroDetectionAlgorithm.CHROMAPRINT, IntroDetectionAlgorithm.FRAME_HASH],
    )
    async def test_runs_only_the_configured_algorithm(
        self,
        algorithm: IntroDetectionAlgorithm,
    ) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)

        chromaprint = _make_detector(result=IntroDetectionResult(markers={}, analyzed_count=2))
        frame_hash = _make_detector(result=IntroDetectionResult(markers={}, analyzed_count=2))
        detectors = {
            IntroDetectionAlgorithm.CHROMAPRINT: chromaprint,
            IntroDetectionAlgorithm.FRAME_HASH: frame_hash,
        }

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=detectors,
            runtime_settings=_make_runtime_settings(
                intro=IntroDetectionConfig(algorithm=algorithm)
            ),
        )
        await job.run()

        chosen = detectors[algorithm]
        other = frame_hash if algorithm is IntroDetectionAlgorithm.CHROMAPRINT else chromaprint
        chosen.detect.assert_called_once()
        other.detect.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_failed_when_algorithm_has_no_registered_detector(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)

        # Registry is missing the configured algorithm — a wiring error
        # that must surface as a FAILED season, not a silent no-op.
        detectors = {
            IntroDetectionAlgorithm.CHROMAPRINT: _make_detector(),
        }

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=detectors,
            runtime_settings=_make_runtime_settings(
                intro=IntroDetectionConfig(algorithm=IntroDetectionAlgorithm.FRAME_HASH)
            ),
        )
        await job.run()

        terminal_state = uow.series.update_season_intro_detection.await_args_list[-1].args[1]
        assert terminal_state == IntroDetectionState.FAILED

    @pytest.mark.asyncio
    async def test_records_audit_run_with_drop_detail(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        factory = MagicMock(return_value=uow)
        # One above the 0.65 floor (persisted), one below (dropped).
        ep1, ep2 = episodes
        markers = {
            ep1.id: DetectedIntro(start_seconds=0.0, end_seconds=70.0, confidence=0.9),
            ep2.id: DetectedIntro(start_seconds=0.0, end_seconds=65.0, confidence=0.5),
        }
        detector = _make_detector(result=IntroDetectionResult(markers=markers, analyzed_count=2))

        job = IntroDetectionJob(
            media_uow_factory=factory,
            intro_detectors=_registry(detector),
            runtime_settings=_make_runtime_settings(),
        )
        await job.run()

        uow.intro_detection_runs.add.assert_awaited_once()
        run = uow.intro_detection_runs.add.await_args.args[0]
        assert run.outcome == IntroDetectionState.COMPLETED
        assert run.detected_count == 2
        assert run.persisted_count == 1
        assert run.min_confidence == pytest.approx(0.65)
        persisted_flags = {r.episode_number: r.persisted for r in run.episode_results}
        assert persisted_flags == {1: True, 2: False}
        # Only the high-confidence marker was actually written.
        assert uow.series.update_episode_intro.await_count == 1

    async def test_logs_series_and_season_at_start(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        job = IntroDetectionJob(
            media_uow_factory=MagicMock(return_value=uow),
            intro_detectors=_registry(_make_detector()),
            runtime_settings=_make_runtime_settings(),
        )

        await job.run()

        # structlog renders to stdout; strip ANSI colour codes (present in
        # CI's console renderer) so the key=value pairs match contiguously.
        raw = capsys.readouterr().out
        out = re.sub(r"\x1b\[[0-9;]*m", "", raw)
        assert "season started" in out
        assert "series_title=Test Series" in out
        assert "season_number=1" in out

    async def test_records_resolved_series_title_on_run(self) -> None:
        sid = SeriesId.generate()
        episodes = [_make_episode(series_id=sid, episode_number=i) for i in (1, 2)]
        season = _make_season(episodes=episodes, series_id=sid)
        uow = _build_uow(pending_seasons=[season])
        job = IntroDetectionJob(
            media_uow_factory=MagicMock(return_value=uow),
            intro_detectors=_registry(_make_detector()),
            runtime_settings=_make_runtime_settings(),
        )

        await job.run()

        uow.intro_detection_runs.add.assert_awaited_once()
        run = uow.intro_detection_runs.add.await_args.args[0]
        assert run.series_title == "Test Series"
