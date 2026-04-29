"""Integration tests for SetEpisodeIntroUseCase / ClearEpisodeIntroUseCase.

These tests drive the use cases through a real ``SqlAlchemyMediaUnitOfWork``
backed by in-memory SQLite, so they exercise the full stack from the
application layer down to persistence (without spinning up a FastAPI
TestClient — the route layer is a thin wrapper that the unit tests
cover directly).
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.application.dtos.intro_dtos import (
    ClearEpisodeIntroInput,
    SetEpisodeIntroInput,
)
from src.modules.media.application.use_cases.clear_episode_intro import (
    ClearEpisodeIntroUseCase,
)
from src.modules.media.application.use_cases.set_episode_intro import SetEpisodeIntroUseCase
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.events import IntroClearedEvent, IntroManuallySetEvent
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    IntroMarker,
    IntroMarkerSource,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemySeriesRepository
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)


def _make_series_with_episode(*, duration_seconds: int = 2700) -> Series:
    sid = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=sid,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(duration_seconds),
        files=[
            MediaFile(
                file_path=FilePath(f"/series/{sid}/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        episodes=[episode],
    )
    return Series(
        id=sid,
        title=Title("Test Series"),
        start_year=Year(2020),
        seasons=[season],
    )


async def _seed(db_session: AsyncSession, series: Series) -> Series:
    repo = SQLAlchemySeriesRepository(db_session)
    await repo.save(series)
    await db_session.commit()
    return series


@pytest.mark.integration
class TestSetEpisodeIntroIntegration:
    """End-to-end tests for SetEpisodeIntroUseCase via real persistence."""

    async def test_persists_marker_to_database(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series = await _seed(db_session, _make_series_with_episode())
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None

        use_case = SetEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
        )
        result = await use_case.execute(
            SetEpisodeIntroInput(
                episode_id=str(episode_id),
                start_seconds=15,
                end_seconds=85,
            )
        )

        assert result.start_seconds == 15
        assert result.end_seconds == 85
        assert result.source == "MANUAL"

        # Re-read with a fresh session to confirm the row was committed.
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
            assert found is not None
            episode = found.seasons[0].episodes[0]
            assert episode.intro is not None
            assert episode.intro.start_seconds == 15
            assert episode.intro.source == IntroMarkerSource.MANUAL

    async def test_dispatches_event_after_commit(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series = await _seed(db_session, _make_series_with_episode())
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None
        event_bus = AsyncMock()

        use_case = SetEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            event_bus=event_bus,
        )
        await use_case.execute(
            SetEpisodeIntroInput(
                episode_id=str(episode_id),
                start_seconds=0,
                end_seconds=60,
            )
        )

        event_bus.publish.assert_awaited_once()
        published = event_bus.publish.await_args.args[0]
        assert isinstance(published, IntroManuallySetEvent)
        assert published.episode_id == str(episode_id)

    async def test_rejects_intro_exceeding_duration(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series = await _seed(
            db_session,
            _make_series_with_episode(duration_seconds=120),
        )
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None

        use_case = SetEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
        )
        with pytest.raises(BusinessRuleViolationException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id=str(episode_id),
                    start_seconds=10,
                    end_seconds=130,
                )
            )

        # Confirm the row was NOT mutated.
        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
            assert found is not None
            assert found.seasons[0].episodes[0].intro is None

    async def test_rejects_invalid_range(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        use_case = SetEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
        )

        with pytest.raises(DomainValidationException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id="epi_abc123abc123",
                    start_seconds=80,
                    end_seconds=60,
                )
            )

    async def test_raises_when_episode_missing(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        use_case = SetEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                SetEpisodeIntroInput(
                    episode_id="epi_missing00000",
                    start_seconds=0,
                    end_seconds=60,
                )
            )


@pytest.mark.integration
class TestClearEpisodeIntroIntegration:
    """End-to-end tests for ClearEpisodeIntroUseCase via real persistence."""

    async def test_clears_persisted_marker(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series = _make_series_with_episode()
        episode = (
            series.seasons[0]
            .episodes[0]
            .with_intro_marker(
                IntroMarker(
                    start_seconds=10,
                    end_seconds=80,
                    source=IntroMarkerSource.MANUAL,
                )
            )
        )
        season = series.seasons[0].with_updates(episodes=[episode])
        series = series.with_updates(seasons=[season])
        await _seed(db_session, series)
        episode_id = episode.id
        assert episode_id is not None
        event_bus = AsyncMock()

        use_case = ClearEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            event_bus=event_bus,
        )
        await use_case.execute(ClearEpisodeIntroInput(episode_id=str(episode_id)))

        async with session_factory() as session:
            repo = SQLAlchemySeriesRepository(session)
            found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
            assert found is not None
            assert found.seasons[0].episodes[0].intro is None

        event_bus.publish.assert_awaited_once()
        assert isinstance(event_bus.publish.await_args.args[0], IntroClearedEvent)

    async def test_idempotent_when_no_marker_present(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series = await _seed(db_session, _make_series_with_episode())
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None
        event_bus = AsyncMock()

        use_case = ClearEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            event_bus=event_bus,
        )
        await use_case.execute(ClearEpisodeIntroInput(episode_id=str(episode_id)))

        event_bus.publish.assert_not_awaited()

    async def test_raises_when_episode_missing(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        use_case = ClearEpisodeIntroUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(ClearEpisodeIntroInput(episode_id="epi_missing00000"))
