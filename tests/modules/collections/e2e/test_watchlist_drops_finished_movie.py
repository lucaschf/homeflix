"""E2E: finishing a movie takes it off the profile's watchlist.

Drives the real progress route and the event wiring ``main.py`` runs at
startup: ``watch_progress`` publishes ``MovieCompletedEvent`` and the
``collections`` handler removes the movie from that profile's watchlist.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.modules.collections.e2e.conftest import SeededUser

from src.main import _subscribe_event_handlers
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.models import WatchlistItemModel
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyWatchlistRepository,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

PROGRESS_PATH = "/api/v1/progress"
_LIBRARY_ID = "lib_finishedmov1"
_DURATION = 7200

type _Login = Callable[..., Awaitable[SeededUser]]


@pytest.fixture(scope="function")
async def subscribed(
    app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncGenerator[None, None]:
    """Subscribe the event handlers the way the app lifespan does.

    The lifespan awaits the providers it resolves because the session
    factory is an async resource; the shared ``app`` fixture overrides it
    with a plain object, so it is overridden back to a resource here.
    """
    container = app.state.container

    async def _session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
        yield session_factory

    container.infrastructure.session_factory.override(providers.Resource(_session_factory))
    await _subscribe_event_handlers(container)
    yield


async def _seed_movie(session_factory: async_sessionmaker[AsyncSession]) -> str:
    movie = Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title("Finished Movie"),
        year=Year(2024),
        duration=Duration(_DURATION),
        files=[
            MediaFile(
                file_path=FilePath(f"/{_LIBRARY_ID}/finished.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)


async def _seed_watchlist(
    session_factory: async_sessionmaker[AsyncSession], *, profile_id: str, media_id: str
) -> None:
    async with session_factory() as session:
        await SQLAlchemyWatchlistRepository(session).add(
            WatchlistItem(
                id=ListId.generate(),
                profile_id=ProfileId(profile_id),
                media_id=media_id,
                media_type=MediaType.MOVIE,
                added_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _live_watchlist(
    session_factory: async_sessionmaker[AsyncSession],
) -> set[tuple[str, str]]:
    """Live ``(profile_id, media_id)`` watchlist rows."""
    async with session_factory() as session:
        result = await session.execute(
            select(WatchlistItemModel.profile_id, WatchlistItemModel.media_id).where(
                WatchlistItemModel.deleted_at.is_(None)
            )
        )
        return {tuple(row) for row in result.all()}


def _progress(movie_id: str, position_seconds: int) -> dict[str, object]:
    return {
        "media_id": movie_id,
        "media_type": "movie",
        "position_seconds": position_seconds,
        "duration_seconds": _DURATION,
    }


@pytest.mark.e2e
@pytest.mark.usefixtures("subscribed")
class TestWatchlistDropsFinishedMovie:
    async def test_finishing_a_movie_takes_it_off_the_watchlist(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        login_with_active_profile: _Login,
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        movie_id = await _seed_movie(session_factory)
        await _seed_watchlist(
            session_factory, profile_id=user.profile_external_id, media_id=movie_id
        )

        response = await client.put(PROGRESS_PATH, json=_progress(movie_id, 6600))

        assert response.status_code == 200
        assert await _live_watchlist(session_factory) == set()

    async def test_partial_progress_keeps_it_on_the_watchlist(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        login_with_active_profile: _Login,
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        movie_id = await _seed_movie(session_factory)
        await _seed_watchlist(
            session_factory, profile_id=user.profile_external_id, media_id=movie_id
        )

        response = await client.put(PROGRESS_PATH, json=_progress(movie_id, 1800))

        assert response.status_code == 200
        assert await _live_watchlist(session_factory) == {(user.profile_external_id, movie_id)}

    async def test_other_profiles_keep_the_movie(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        login_with_active_profile: _Login,
    ) -> None:
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        movie_id = await _seed_movie(session_factory)
        other_profile = ProfileId.generate().value
        for profile_id in (user.profile_external_id, other_profile):
            await _seed_watchlist(session_factory, profile_id=profile_id, media_id=movie_id)

        response = await client.put(PROGRESS_PATH, json=_progress(movie_id, 6600))

        assert response.status_code == 200
        assert await _live_watchlist(session_factory) == {(other_profile, movie_id)}
