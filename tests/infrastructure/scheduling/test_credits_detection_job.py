"""Tests for CreditsDetectionJob.

Mocks the media UoW factory and the per-file detector so the tests
exercise orchestration (per-title state transitions, confidence floor,
MANUAL skip, error handling) without touching ffmpeg or the database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.credits_detection_job import CreditsDetectionJob
from src.modules.media.application.ports import DetectedCredits
from src.modules.media.application.ports.credits_detector_port import CreditsSignal
from src.modules.media.domain.entities import Episode, Movie
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    CreditsMarkerSource,
    Duration,
    EpisodeNumber,
    FilePath,
    MediaFile,
    Resolution,
    SeasonNumber,
    SeriesId,
    Title,
    Year,
)
from src.modules.settings.domain.value_objects import CreditsDetectionConfig


def _file(path: str) -> MediaFile:
    return MediaFile(
        file_path=FilePath(path),
        file_size=1_000_000_000,
        resolution=Resolution("1080p"),
        is_primary=True,
    )


def _movie(*, credits: CreditsMarker | None = None) -> Movie:
    movie = Movie(
        id=None,
        library_id="lib_x",
        title=Title("A Movie"),
        year=Year(2020),
        duration=Duration(6000),
        files=[_file("/movies/a.mkv")],
        credits=credits,
    )
    return movie.with_updates(id="mov_aaaaaaaaaaaa")


def _episode(*, credits: CreditsMarker | None = None) -> Episode:
    return Episode(
        id="epi_bbbbbbbbbbbb",
        series_id=SeriesId.generate(),
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("An Episode"),
        duration=Duration(2700),
        files=[_file("/series/s01e01.mkv")],
        credits=credits,
    )


def _build_uow(*, movies: list[Movie], episodes: list[Episode]) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.series = AsyncMock()
    uow.movies.find_pending_credits_detection = AsyncMock(return_value=movies)
    uow.series.find_episodes_pending_credits_detection = AsyncMock(return_value=episodes)
    uow.movies.update_movie_credits = AsyncMock(return_value=True)
    uow.series.update_episode_credits = AsyncMock(return_value=True)
    return uow


def _detector(*, result: DetectedCredits | None = None, raises: bool = False) -> MagicMock:
    detector = MagicMock()
    if raises:
        detector.detect.side_effect = RuntimeError("ffmpeg boom")
    else:
        detector.detect.return_value = result
    return detector


def _runtime(config: CreditsDetectionConfig | None = None) -> AsyncMock:
    runtime = AsyncMock()
    runtime.credits_detection = AsyncMock(return_value=config or CreditsDetectionConfig())
    return runtime


def _states(update_mock: AsyncMock) -> list[CreditsDetectionState]:
    """The detection states passed across all calls of an update mock."""
    return [call.args[2] for call in update_mock.await_args_list]


@pytest.mark.unit
class TestCreditsDetectionJob:
    """Orchestration tests for CreditsDetectionJob.run."""

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_pending(self) -> None:
        uow = _build_uow(movies=[], episodes=[])
        job = CreditsDetectionJob(MagicMock(return_value=uow), _detector(), _runtime())
        await job.run()
        uow.movies.update_movie_credits.assert_not_awaited()
        uow.series.update_episode_credits.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_persists_marker_when_confidence_clears_floor(self) -> None:
        uow = _build_uow(movies=[_movie()], episodes=[])
        detector = _detector(
            result=DetectedCredits(start_seconds=5400.0, confidence=0.9, signal=CreditsSignal.EDGE)
        )
        job = CreditsDetectionJob(MagicMock(return_value=uow), detector, _runtime())

        await job.run()

        # IN_PROGRESS claim, then COMPLETED with a marker.
        assert _states(uow.movies.update_movie_credits) == [
            CreditsDetectionState.IN_PROGRESS,
            CreditsDetectionState.COMPLETED,
        ]
        marker = uow.movies.update_movie_credits.await_args_list[-1].args[1]
        assert isinstance(marker, CreditsMarker)
        assert marker.start_seconds == 5400
        assert marker.source is CreditsMarkerSource.AUTO_DETECTED

    @pytest.mark.asyncio
    async def test_no_credits_found_when_below_floor(self) -> None:
        uow = _build_uow(movies=[_movie()], episodes=[])
        detector = _detector(
            result=DetectedCredits(
                start_seconds=5400.0, confidence=0.1, signal=CreditsSignal.MOTION
            )
        )
        config = CreditsDetectionConfig(min_confidence=0.5)
        job = CreditsDetectionJob(MagicMock(return_value=uow), detector, _runtime(config))

        await job.run()

        last = uow.movies.update_movie_credits.await_args_list[-1]
        assert last.args[1] is None
        assert last.args[2] is CreditsDetectionState.NO_CREDITS_FOUND

    @pytest.mark.asyncio
    async def test_no_credits_found_when_detector_returns_none(self) -> None:
        uow = _build_uow(movies=[], episodes=[_episode()])
        job = CreditsDetectionJob(MagicMock(return_value=uow), _detector(result=None), _runtime())

        await job.run()

        assert _states(uow.series.update_episode_credits)[-1] is (
            CreditsDetectionState.NO_CREDITS_FOUND
        )

    @pytest.mark.asyncio
    async def test_failed_when_detector_raises(self) -> None:
        uow = _build_uow(movies=[_movie()], episodes=[])
        job = CreditsDetectionJob(MagicMock(return_value=uow), _detector(raises=True), _runtime())

        await job.run()

        assert _states(uow.movies.update_movie_credits)[-1] is CreditsDetectionState.FAILED

    @pytest.mark.asyncio
    async def test_skips_manual_marker(self) -> None:
        manual = CreditsMarker(start_seconds=100, source=CreditsMarkerSource.MANUAL)
        uow = _build_uow(movies=[_movie(credits=manual)], episodes=[])
        detector = _detector(
            result=DetectedCredits(start_seconds=1.0, confidence=1.0, signal=CreditsSignal.EDGE)
        )
        job = CreditsDetectionJob(MagicMock(return_value=uow), detector, _runtime())

        await job.run()

        uow.movies.update_movie_credits.assert_not_awaited()
        detector.detect.assert_not_called()
