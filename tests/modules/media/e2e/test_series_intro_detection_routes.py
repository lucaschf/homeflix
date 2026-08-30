"""End-to-end tests for the season intro-detection reset endpoint."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    EpisodeNumber,
    FilePath,
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
    IntroStatus,
    MediaFile,
    Resolution,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemySeriesRepository,
)
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
_LIBRARY_ID = "lib_test12345678"


def _reset_path(season_id: str, *, run_now: bool | None = None) -> str:
    path = f"/api/v1/series/seasons/{season_id}/intro-detection/reset"
    return path if run_now is None else f"{path}?run_now={str(run_now).lower()}"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


async def _login_as_admin(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
) -> None:
    admin = await seed(email="admin@example.com", is_admin=True)
    await _login(client, admin)


async def _seed_completed_season(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Insert a one-episode series whose season is already COMPLETED."""
    series_id = SeriesId.generate()
    season_id = SeasonId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("Episode 1"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(f"/series/{series_id}/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    series = Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title("Intro Series"),
        start_year=Year(2020),
        seasons=[
            Season(
                id=season_id,
                series_id=series_id,
                season_number=SeasonNumber(1),
                title=Title("Season 1"),
                episodes=[episode],
                intro_detection_state=IntroDetectionState.COMPLETED,
            )
        ],
    )
    async with session_factory() as session:
        await SQLAlchemySeriesRepository(session).save(series)
        await session.commit()
    return str(season_id)


async def _seed_episode(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    intro: IntroMarker | None = None,
) -> tuple[str, str]:
    """Insert a one-episode series; return ``(series_id, episode_id)``."""
    series_id = SeriesId.generate()
    episode_id = EpisodeId.generate()
    episode = Episode(
        id=episode_id,
        series_id=series_id,
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("Episode 1"),
        duration=Duration(2700),
        intro=intro,
        files=[
            MediaFile(
                file_path=FilePath(f"/series/{series_id}/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    series = Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title("Intro Series"),
        start_year=Year(2020),
        seasons=[
            Season(
                id=SeasonId.generate(),
                series_id=series_id,
                season_number=SeasonNumber(1),
                title=Title("Season 1"),
                episodes=[episode],
            )
        ],
    )
    async with session_factory() as session:
        await SQLAlchemySeriesRepository(session).save(series)
        await session.commit()
    return str(series_id), str(episode_id)


def _absent_path(episode_id: str) -> str:
    return f"/api/v1/series/episodes/{episode_id}/intro/absent"


async def _episode_state(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: str,
) -> Episode:
    """Read the episode back from the repository.

    The catalog GET needs an active *profile*, not just an admin login,
    so the effect of these admin-only routes is verified against the
    persisted row instead of a second endpoint.
    """
    async with session_factory() as session:
        series = await SQLAlchemySeriesRepository(session).find_by_id(SeriesId(series_id))
    assert series is not None
    return series.seasons[0].episodes[0]


@pytest.mark.e2e
class TestResetSeasonIntroDetectionAuth:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(_reset_path(str(SeasonId.generate())))
        assert resp.status_code == 401

    async def test_member_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        resp = await client.post(_reset_path(str(SeasonId.generate())))

        assert resp.status_code == 403


@pytest.mark.e2e
class TestResetSeasonIntroDetection:
    async def test_unknown_season_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        resp = await client.post(_reset_path(str(SeasonId.generate())))

        assert resp.status_code == 404

    async def test_requeues_without_starting_a_run_by_default(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        season_id = await _seed_completed_season(session_factory)

        resp = await client.post(_reset_path(season_id))

        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "intro_detection_reset"
        assert body["data"]["detection_started"] is False

    async def test_run_now_starts_a_detection_run(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The reset commits and reports that a run was launched.

        The run itself is fire-and-forget (it needs ffmpeg), so this
        only asserts the response contract — the season's own state and
        the run history carry the outcome.
        """
        await _login_as_admin(client, seed_user_with_profile)
        season_id = await _seed_completed_season(session_factory)

        resp = await client.post(_reset_path(season_id, run_now=True))

        assert resp.status_code == 200
        assert resp.json()["data"]["detection_started"] is True


@pytest.mark.e2e
class TestMarkEpisodeIntroAbsent:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(_absent_path(str(EpisodeId.generate())))
        assert resp.status_code == 401

    async def test_member_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        resp = await client.post(_absent_path(str(EpisodeId.generate())))

        assert resp.status_code == 403

    async def test_unknown_episode_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        resp = await client.post(_absent_path(str(EpisodeId.generate())))

        assert resp.status_code == 404

    async def test_marks_a_pending_episode_as_absent(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        series_id, episode_id = await _seed_episode(session_factory)
        assert (
            await _episode_state(session_factory, series_id)
        ).intro_status is IntroStatus.PENDING

        resp = await client.post(_absent_path(episode_id))

        assert resp.status_code == 204
        assert (await _episode_state(session_factory, series_id)).intro_status is IntroStatus.ABSENT

    async def test_drops_an_existing_marker(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        marker = IntroMarker(start_seconds=10, end_seconds=80, source=IntroMarkerSource.MANUAL)
        series_id, episode_id = await _seed_episode(session_factory, intro=marker)
        assert (await _episode_state(session_factory, series_id)).intro_status is IntroStatus.MARKED

        await client.post(_absent_path(episode_id))

        episode = await _episode_state(session_factory, series_id)
        assert episode.intro_status is IntroStatus.ABSENT
        assert episode.intro is None

    async def test_clearing_reopens_the_verdict(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE is the single undo for either intro decision."""
        await _login_as_admin(client, seed_user_with_profile)
        series_id, episode_id = await _seed_episode(session_factory)
        await client.post(_absent_path(episode_id))

        resp = await client.delete(f"/api/v1/series/episodes/{episode_id}/intro")

        assert resp.status_code == 204
        assert (
            await _episode_state(session_factory, series_id)
        ).intro_status is IntroStatus.PENDING

    async def test_is_idempotent(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)
        series_id, episode_id = await _seed_episode(session_factory)

        assert (await client.post(_absent_path(episode_id))).status_code == 204
        assert (await client.post(_absent_path(episode_id))).status_code == 204
        assert (await _episode_state(session_factory, series_id)).intro_status is IntroStatus.ABSENT
