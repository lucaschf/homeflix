"""Tests for SetEpisodeIntroUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.application.dtos.intro_dtos import (
    IntroMarkerOutput,
    SetEpisodeIntroInput,
)
from src.modules.media.application.use_cases.set_episode_intro import SetEpisodeIntroUseCase
from src.modules.media.domain.entities import Episode
from src.modules.media.domain.events import IntroManuallySetEvent
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeriesId,
    Title,
)
from tests.modules.media.unit.conftest import make_media_uow_mock


def _make_episode(duration_seconds: int = 2700) -> Episode:
    return Episode(
        id=EpisodeId.generate(),
        series_id=SeriesId.generate(),
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(duration_seconds),
        files=[
            MediaFile(
                file_path=FilePath("/series/show/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


@pytest.mark.unit
class TestSetEpisodeIntroUseCase:
    """Tests for SetEpisodeIntroUseCase."""

    @pytest.mark.asyncio
    async def test_persists_marker_and_returns_output(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode()
        mocks.series.find_episode_by_id.return_value = episode
        mocks.series.update_episode_intro.return_value = True
        event_bus = AsyncMock()

        use_case = SetEpisodeIntroUseCase(
            uow_factory=mocks.factory,
            event_bus=event_bus,
        )
        result = await use_case.execute(
            SetEpisodeIntroInput(
                episode_id=str(episode.id),
                start_seconds=10,
                end_seconds=80,
            )
        )

        assert isinstance(result, IntroMarkerOutput)
        assert result.start_seconds == 10
        assert result.end_seconds == 80
        assert result.source == "MANUAL"
        assert result.confidence is None

        mocks.series.update_episode_intro.assert_awaited_once()
        # ``await_args_list[0]`` is explicit about which call we are
        # inspecting; the surrounding ``assert_awaited_once`` already
        # guards that there is exactly one. ``assert_awaited_once_with``
        # cannot be used directly — IntroMarker.detected_at is auto-
        # generated, so equality on the marker fails.
        first_call = mocks.series.update_episode_intro.await_args_list[0]
        assert first_call.args[0] == episode.id
        assert first_call.args[1].source.value == "MANUAL"
        assert first_call.args[1].start_seconds == 10
        assert first_call.args[1].end_seconds == 80

    @pytest.mark.asyncio
    async def test_dispatches_intro_manually_set_event(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode()
        mocks.series.find_episode_by_id.return_value = episode
        event_bus = AsyncMock()

        use_case = SetEpisodeIntroUseCase(
            uow_factory=mocks.factory,
            event_bus=event_bus,
        )
        await use_case.execute(
            SetEpisodeIntroInput(
                episode_id=str(episode.id),
                start_seconds=5,
                end_seconds=70,
            )
        )

        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.await_args_list[0].args[0]
        assert isinstance(published_event, IntroManuallySetEvent)
        assert published_event.episode_id == str(episode.id)
        assert published_event.series_id == str(episode.series_id)
        assert published_event.start_seconds == 5
        assert published_event.end_seconds == 70

    @pytest.mark.asyncio
    async def test_works_without_event_bus(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode()
        mocks.series.find_episode_by_id.return_value = episode

        use_case = SetEpisodeIntroUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            SetEpisodeIntroInput(
                episode_id=str(episode.id),
                start_seconds=0,
                end_seconds=60,
            )
        )

        assert result.start_seconds == 0
        mocks.series.update_episode_intro.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_episode_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_episode_by_id.return_value = None

        use_case = SetEpisodeIntroUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id="epi_missing00000",
                    start_seconds=0,
                    end_seconds=60,
                )
            )
        mocks.series.update_episode_intro.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_intro_exceeds_duration(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode(duration_seconds=120)
        mocks.series.find_episode_by_id.return_value = episode

        use_case = SetEpisodeIntroUseCase(uow_factory=mocks.factory)

        with pytest.raises(BusinessRuleViolationException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id=str(episode.id),
                    start_seconds=10,
                    end_seconds=130,
                )
            )
        mocks.series.update_episode_intro.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_end_not_greater_than_start(self) -> None:
        mocks = make_media_uow_mock()

        use_case = SetEpisodeIntroUseCase(uow_factory=mocks.factory)

        with pytest.raises(DomainValidationException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id="epi_abc123abc123",
                    start_seconds=60,
                    end_seconds=60,
                )
            )
        mocks.series.find_episode_by_id.assert_not_awaited()
