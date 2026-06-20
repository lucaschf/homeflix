"""Tests for the manual credits-marker use cases (set/clear/reset).

Mocks the media UoW so the tests exercise the movie/episode dispatch,
the MANUAL marker + state transitions, and the not-found / wrong-type
guards — without a database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.application.dtos.credits_dtos import (
    ResetCreditsDetectionInput,
    SetCreditsMarkerInput,
)
from src.modules.media.application.use_cases.clear_credits_marker import (
    ClearCreditsMarkerUseCase,
)
from src.modules.media.application.use_cases.reset_credits_detection import (
    ResetCreditsDetectionUseCase,
)
from src.modules.media.application.use_cases.set_credits_marker import SetCreditsMarkerUseCase
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

_MOVIE_ID = "mov_aaaaaaaaaaaa"
_EPISODE_ID = "epi_bbbbbbbbbbbb"


def _movie(*, credits: CreditsMarker | None = None) -> Movie:
    return Movie(
        id=_MOVIE_ID,
        library_id="lib_x",
        title=Title("A Movie"),
        year=Year(2020),
        duration=Duration(6000),
        files=[
            MediaFile(
                file_path=FilePath("/movies/a.mkv"),
                file_size=1,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        credits=credits,
    )


def _episode() -> Episode:
    return Episode(
        id=_EPISODE_ID,
        series_id=SeriesId.generate(),
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("An Episode"),
        duration=Duration(2700),
    )


def _uow(*, movie: Movie | None = None, episode: Episode | None = None) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.series = AsyncMock()
    uow.movies.find_by_id = AsyncMock(return_value=movie)
    uow.series.find_episode_by_id = AsyncMock(return_value=episode)
    uow.movies.update_movie_credits = AsyncMock(return_value=True)
    uow.series.update_episode_credits = AsyncMock(return_value=True)
    return uow


@pytest.mark.unit
class TestSetCreditsMarker:
    @pytest.mark.asyncio
    async def test_sets_manual_marker_on_movie(self) -> None:
        uow = _uow(movie=_movie())
        use_case = SetCreditsMarkerUseCase(MagicMock(return_value=uow))

        out = await use_case.execute(SetCreditsMarkerInput(media_id=_MOVIE_ID, start_seconds=5400))

        assert out.start_seconds == 5400
        assert out.source == CreditsMarkerSource.MANUAL.value
        marker, state = uow.movies.update_movie_credits.await_args.args[1:3]
        assert marker.source is CreditsMarkerSource.MANUAL
        assert state is CreditsDetectionState.COMPLETED

    @pytest.mark.asyncio
    async def test_dispatches_to_episode(self) -> None:
        uow = _uow(episode=_episode())
        use_case = SetCreditsMarkerUseCase(MagicMock(return_value=uow))

        await use_case.execute(SetCreditsMarkerInput(media_id=_EPISODE_ID, start_seconds=120))

        uow.series.update_episode_credits.assert_awaited_once()
        uow.movies.update_movie_credits.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_404_when_missing(self) -> None:
        uow = _uow(movie=None)
        use_case = SetCreditsMarkerUseCase(MagicMock(return_value=uow))
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(SetCreditsMarkerInput(media_id=_MOVIE_ID, start_seconds=1))

    @pytest.mark.asyncio
    async def test_404_when_not_creditable_id(self) -> None:
        uow = _uow()
        use_case = SetCreditsMarkerUseCase(MagicMock(return_value=uow))
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetCreditsMarkerInput(media_id="ser_cccccccccccc", start_seconds=1)
            )

    @pytest.mark.asyncio
    async def test_rejects_onset_beyond_duration(self) -> None:
        uow = _uow(movie=_movie())
        use_case = SetCreditsMarkerUseCase(MagicMock(return_value=uow))
        with pytest.raises(BusinessRuleViolationException):
            await use_case.execute(SetCreditsMarkerInput(media_id=_MOVIE_ID, start_seconds=999999))


@pytest.mark.unit
class TestClearCreditsMarker:
    @pytest.mark.asyncio
    async def test_clears_marker_and_keeps_completed(self) -> None:
        marker = CreditsMarker(start_seconds=5400, source=CreditsMarkerSource.MANUAL)
        uow = _uow(movie=_movie(credits=marker))
        use_case = ClearCreditsMarkerUseCase(MagicMock(return_value=uow))

        await use_case.execute(_MOVIE_ID)

        passed_marker, state = uow.movies.update_movie_credits.await_args.args[1:3]
        assert passed_marker is None
        assert state is CreditsDetectionState.COMPLETED


@pytest.mark.unit
class TestResetCreditsDetection:
    @pytest.mark.asyncio
    async def test_clears_auto_and_requeues(self) -> None:
        auto = CreditsMarker(
            start_seconds=5400, source=CreditsMarkerSource.AUTO_DETECTED, confidence=0.9
        )
        uow = _uow(movie=_movie(credits=auto))
        use_case = ResetCreditsDetectionUseCase(MagicMock(return_value=uow))

        out = await use_case.execute(ResetCreditsDetectionInput(media_id=_MOVIE_ID))

        assert out.marker_cleared is True
        passed_marker, state = uow.movies.update_movie_credits.await_args.args[1:3]
        assert passed_marker is None
        assert state is CreditsDetectionState.NOT_STARTED

    @pytest.mark.asyncio
    async def test_preserves_manual_marker(self) -> None:
        manual = CreditsMarker(start_seconds=5400, source=CreditsMarkerSource.MANUAL)
        uow = _uow(movie=_movie(credits=manual))
        use_case = ResetCreditsDetectionUseCase(MagicMock(return_value=uow))

        out = await use_case.execute(ResetCreditsDetectionInput(media_id=_MOVIE_ID))

        assert out.marker_cleared is False
        passed_marker, state = uow.movies.update_movie_credits.await_args.args[1:3]
        assert passed_marker is manual
        assert state is CreditsDetectionState.NOT_STARTED
