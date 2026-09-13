"""End-to-end tests for the detail and playback maturity gate (ADR-035 §11).

Drives the real routes over the in-process ASGI transport against an
in-memory database. ``Profile`` has no maturity limit yet, so the
production ``ProfileViewingPolicyAdapter`` can only build library-only
policies and the 403 is unreachable in production; the media
container's ``profile_viewing_policy`` provider is overridden with a
policy that carries a limit, which is the only way to see the contract
the web client will receive.

Covers both surfaces that reach ``GetMovieByIdUseCase`` /
``GetSeriesByIdUseCase``: the catalog detail routes, and the streaming
routes, which delegate to those use cases through
``MediaPlaybackLookupAdapter`` and let their errors propagate to the
global handler untranslated.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
_LIBRARY_ID = "lib_maturity0001"
_OTHER_LIBRARY_ID = "lib_otherlib0001"
_LIMIT = 12


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


@pytest.fixture(scope="function")
async def limited_profile(app: FastAPI) -> AsyncGenerator[None, None]:
    """Resolve every profile to one library with a maturity limit of 12."""
    provider = app.state.container.media.profile_viewing_policy
    provider.override(
        providers.Object(
            _FixedViewingPolicy(
                ViewingPolicy(
                    allowed_library_ids=[_LIBRARY_ID],
                    maturity_limit=AgeRating(_LIMIT),
                )
            )
        )
    )
    yield
    provider.reset_last_overriding()


def _certification(label: str, age: int | None) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS if age is not None else RatingSystem.UNKNOWN,
        label=ContentRating(label),
        minimum_age=AgeRating(age) if age is not None else None,
    )


async def _seed_movie(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    title: str,
    certification: Certification | None,
    library_id: str = _LIBRARY_ID,
) -> str:
    movie = Movie(
        library_id=library_id,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{library_id}/{title}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        certification=certification,
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)


async def _seed_series(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    title: str,
    certification: Certification | None,
) -> str:
    series_id = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(f"/{_LIBRARY_ID}/{title}/s01e01.mkv"),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    series = Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title(title),
        start_year=Year(2020),
        seasons=[
            Season(
                id=SeasonId.generate(),
                series_id=series_id,
                season_number=1,
                title=Title("Season 1"),
                episodes=[episode],
            )
        ],
        certification=certification,
    )
    async with session_factory() as session:
        saved = await SQLAlchemySeriesRepository(session).save(series)
        await session.commit()
    return str(saved.id)


async def _login_with_active_profile(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
) -> None:
    user = await seed()
    login = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert login.status_code == 204
    switch = await client.post(f"/api/v1/profiles/{user.profile_external_id}/switch")
    assert switch.status_code == 204


def _assert_maturity_403(response, *, title: str, required_age: int) -> None:
    assert response.status_code == 403
    body = response.json()
    assert body["type"] == "permission_error"
    assert body["code"] == "CONTENT_RESTRICTED_BY_MATURITY"
    assert body["message"]
    assert body["details"] == [
        {
            "code": "CONTENT_RESTRICTED_BY_MATURITY",
            "message": f"Requires age {required_age}; profile limit is {_LIMIT}",
            "metadata": {"required_age": required_age, "profile_limit": _LIMIT},
        }
    ]
    assert title not in response.text


@pytest.mark.e2e
@pytest.mark.usefixtures("limited_profile")
class TestDetailMaturityGate:
    """Catalog detail routes: 404 on the library axis, 403 on the age axis."""

    async def test_movie_above_limit_returns_403_without_the_title(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Sixteen Plus Movie"
        movie_id = await _seed_movie(
            session_factory, title=title, certification=_certification("16", 16)
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/movies/{movie_id}")

        _assert_maturity_403(response, title=title, required_age=16)

    async def test_series_above_limit_returns_403_without_the_title(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Sixteen Plus Show"
        series_id = await _seed_series(
            session_factory, title=title, certification=_certification("16", 16)
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/series/{series_id}")

        _assert_maturity_403(response, title=title, required_age=16)

    async def test_unrated_movie_returns_the_distinct_unrated_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Unrated Movie"
        movie_id = await _seed_movie(session_factory, title=title, certification=None)
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/movies/{movie_id}")

        assert response.status_code == 403
        body = response.json()
        assert body["type"] == "permission_error"
        assert body["code"] == "CONTENT_RESTRICTED_UNRATED"
        assert body["details"][0]["metadata"] == {"profile_limit": _LIMIT}
        assert title not in response.text

    async def test_movie_outside_libraries_still_returns_404(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Other Shelf Movie"
        movie_id = await _seed_movie(
            session_factory,
            title=title,
            certification=_certification("18", 18),
            library_id=_OTHER_LIBRARY_ID,
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/movies/{movie_id}")

        assert response.status_code == 404
        assert title not in response.text

    async def test_movie_within_limit_returns_200(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(
            session_factory, title="Ten Plus Movie", certification=_certification("10", 10)
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/movies/{movie_id}")

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Ten Plus Movie"


@pytest.mark.e2e
@pytest.mark.usefixtures("limited_profile")
class TestPlaybackMaturityGate:
    """Streaming routes surface the same 403 — not a 404, not a 500."""

    async def test_movie_hls_playlist_above_limit_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Sixteen Plus Movie"
        movie_id = await _seed_movie(
            session_factory, title=title, certification=_certification("16", 16)
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/stream/movie/{movie_id}/hls/playlist.m3u8")

        _assert_maturity_403(response, title=title, required_age=16)

    async def test_episode_hls_playlist_above_limit_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Sixteen Plus Show"
        series_id = await _seed_series(
            session_factory, title=title, certification=_certification("16", 16)
        )
        await _login_with_active_profile(client, seed_user_with_profile)

        response = await client.get(f"/api/v1/stream/episode/{series_id}/1/1/hls/playlist.m3u8")

        _assert_maturity_403(response, title=title, required_age=16)
