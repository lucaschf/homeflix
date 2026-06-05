"""Tests for ClearEpisodeIntroUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_dtos import ClearEpisodeIntroInput
from src.modules.media.application.use_cases.clear_episode_intro import (
    ClearEpisodeIntroUseCase,
)
from src.modules.media.domain.entities import Episode
from src.modules.media.domain.events import IntroClearedEvent
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    IntroMarker,
    IntroMarkerSource,
    MediaFile,
    Resolution,
    SeriesId,
    Title,
)
from tests.modules.media.unit.conftest import make_media_uow_mock


def _make_episode(*, with_marker: bool = True) -> Episode:
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=SeriesId.generate(),
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/show/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    if with_marker:
        episode = episode.with_intro_marker(
            IntroMarker(
                start_seconds=10,
                end_seconds=80,
                source=IntroMarkerSource.MANUAL,
            )
        )
    return episode


@pytest.mark.unit
class TestClearEpisodeIntroUseCase:
    """Tests for ClearEpisodeIntroUseCase."""

    @pytest.mark.asyncio
    async def test_clears_existing_marker_and_dispatches_event(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode(with_marker=True)
        mocks.series.find_episode_by_id.return_value = episode
        event_bus = AsyncMock()

        use_case = ClearEpisodeIntroUseCase(
            uow_factory=mocks.factory,
            event_bus=event_bus,
        )
        await use_case.execute(ClearEpisodeIntroInput(episode_id=str(episode.id)))

        mocks.series.update_episode_intro.assert_awaited_once_with(episode.id, None)
        event_bus.publish.assert_awaited_once()
        published_event = event_bus.publish.await_args_list[0].args[0]
        assert isinstance(published_event, IntroClearedEvent)
        assert published_event.episode_id == episode.id
        assert published_event.series_id == episode.series_id

    @pytest.mark.asyncio
    async def test_idempotent_when_marker_already_absent(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode(with_marker=False)
        mocks.series.find_episode_by_id.return_value = episode
        event_bus = AsyncMock()

        use_case = ClearEpisodeIntroUseCase(
            uow_factory=mocks.factory,
            event_bus=event_bus,
        )
        await use_case.execute(ClearEpisodeIntroInput(episode_id=str(episode.id)))

        mocks.series.update_episode_intro.assert_not_awaited()
        event_bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_episode_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_episode_by_id.return_value = None

        use_case = ClearEpisodeIntroUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(ClearEpisodeIntroInput(episode_id="epi_missing00000"))
        mocks.series.update_episode_intro.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_works_without_event_bus(self) -> None:
        mocks = make_media_uow_mock()
        episode = _make_episode(with_marker=True)
        mocks.series.find_episode_by_id.return_value = episode

        use_case = ClearEpisodeIntroUseCase(uow_factory=mocks.factory)
        await use_case.execute(ClearEpisodeIntroInput(episode_id=str(episode.id)))

        mocks.series.update_episode_intro.assert_awaited_once()
