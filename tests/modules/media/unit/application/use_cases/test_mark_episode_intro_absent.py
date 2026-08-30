"""Tests for MarkEpisodeIntroAbsentUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_dtos import MarkEpisodeIntroAbsentInput
from src.modules.media.application.use_cases.mark_episode_intro_absent import (
    MarkEpisodeIntroAbsentUseCase,
)
from src.modules.media.domain.events import IntroMarkedAbsentEvent
from src.modules.media.domain.value_objects import EpisodeId, SeriesId


def _build_uow(*, episode: object | None) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.series = AsyncMock()
    uow.series.find_episode_by_id = AsyncMock(return_value=episode)
    uow.series.mark_episode_intro_absent = AsyncMock(return_value=True)
    return uow


def _episode(*, absent_at: datetime | None = None) -> MagicMock:
    episode = MagicMock()
    episode.intro_absent_at = absent_at
    episode.series_id = SeriesId.generate()
    return episode


@pytest.mark.unit
class TestMarkEpisodeIntroAbsentUseCase:
    @pytest.mark.asyncio
    async def test_flags_the_episode_and_publishes_the_event(self) -> None:
        episode_id = EpisodeId.generate()
        uow = _build_uow(episode=_episode())
        bus = AsyncMock()
        use_case = MarkEpisodeIntroAbsentUseCase(MagicMock(return_value=uow), event_bus=bus)

        await use_case.execute(MarkEpisodeIntroAbsentInput(episode_id=str(episode_id)))

        uow.series.mark_episode_intro_absent.assert_awaited_once()
        assert uow.series.mark_episode_intro_absent.await_args.args[0] == episode_id
        bus.publish.assert_awaited_once()
        assert isinstance(bus.publish.await_args.args[0], IntroMarkedAbsentEvent)

    @pytest.mark.asyncio
    async def test_raises_when_episode_not_found(self) -> None:
        uow = _build_uow(episode=None)
        use_case = MarkEpisodeIntroAbsentUseCase(MagicMock(return_value=uow))

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                MarkEpisodeIntroAbsentInput(episode_id=str(EpisodeId.generate()))
            )

        uow.series.mark_episode_intro_absent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_is_idempotent_for_an_already_absent_episode(self) -> None:
        """Re-marking succeeds but writes nothing and emits no event."""
        uow = _build_uow(episode=_episode(absent_at=datetime(2026, 8, 29, tzinfo=UTC)))
        bus = AsyncMock()
        use_case = MarkEpisodeIntroAbsentUseCase(MagicMock(return_value=uow), event_bus=bus)

        await use_case.execute(MarkEpisodeIntroAbsentInput(episode_id=str(EpisodeId.generate())))

        uow.series.mark_episode_intro_absent.assert_not_awaited()
        bus.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_works_without_an_event_bus(self) -> None:
        uow = _build_uow(episode=_episode())
        use_case = MarkEpisodeIntroAbsentUseCase(MagicMock(return_value=uow))

        await use_case.execute(MarkEpisodeIntroAbsentInput(episode_id=str(EpisodeId.generate())))

        uow.series.mark_episode_intro_absent.assert_awaited_once()
