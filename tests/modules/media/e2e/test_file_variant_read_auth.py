"""End-to-end tests for the auth gate on the file-variant read routes.

``GET /api/v1/movies/{movie_id}/files`` and
``GET /api/v1/series/episodes/{episode_id}/files`` return every variant's
absolute ``file_path``, which on a real library embeds the title. Their
write-side siblings (POST / DELETE / PUT primary) were already
admin-only; the reads now match. No web-client screen calls them.

Each route is driven as an anonymous caller (401), a member (403) and an
admin (200 with the variant list). The path must never reach a caller
that is not an admin, not even inside an error envelope.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from tests.modules.media.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
_LIBRARY_ID = "lib_filesauth001"
_MOVIE_PATH = "/mnt/media/movies/Secret Movie (2024)/Secret Movie (2024).mkv"
_EPISODE_PATH = "/mnt/media/series/Secret Show/Season 01/Secret Show - S01E01.mkv"


@dataclass(frozen=True)
class _SeededVariant:
    """A seeded title's ``/files`` URL and the path its variant carries."""

    url: str
    file_path: str


def _media_file(path: str) -> MediaFile:
    return MediaFile(
        file_path=FilePath(path),
        file_size=1_000_000_000,
        resolution=Resolution("1080p"),
        is_primary=True,
    )


async def _seed_movie(session_factory: async_sessionmaker[AsyncSession]) -> _SeededVariant:
    movie = Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title("Secret Movie"),
        year=Year(2024),
        duration=Duration(7200),
        files=[_media_file(_MOVIE_PATH)],
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return _SeededVariant(url=f"/api/v1/movies/{saved.id}/files", file_path=_MOVIE_PATH)


async def _seed_episode(session_factory: async_sessionmaker[AsyncSession]) -> _SeededVariant:
    series_id = SeriesId.generate()
    episode_id = EpisodeId.generate()
    series = Series(
        library_id=_LIBRARY_ID,
        id=series_id,
        title=Title("Secret Show"),
        start_year=Year(2020),
        seasons=[
            Season(
                id=SeasonId.generate(),
                series_id=series_id,
                season_number=1,
                title=Title("Season 1"),
                episodes=[
                    Episode(
                        id=episode_id,
                        series_id=series_id,
                        season_number=1,
                        episode_number=1,
                        title=Title("Pilot"),
                        duration=Duration(2700),
                        files=[_media_file(_EPISODE_PATH)],
                    )
                ],
            )
        ],
    )
    async with session_factory() as session:
        await SQLAlchemySeriesRepository(session).save(series)
        await session.commit()
    return _SeededVariant(
        url=f"/api/v1/series/episodes/{episode_id}/files", file_path=_EPISODE_PATH
    )


_SEEDERS = {"movie": _seed_movie, "episode": _seed_episode}


@pytest.fixture(params=sorted(_SEEDERS))
async def variant(
    request: pytest.FixtureRequest,
    session_factory: async_sessionmaker[AsyncSession],
) -> _SeededVariant:
    """Seed one movie or one episode with a single file variant."""
    return await _SEEDERS[request.param](session_factory)


async def _login(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
    *,
    is_admin: bool,
) -> None:
    user = await seed(
        email="admin@example.com" if is_admin else "member@example.com", is_admin=is_admin
    )
    response = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert response.status_code == 204


@pytest.mark.e2e
class TestFileVariantReadAuth:
    """``GET .../files`` is admin-only and never leaks the path otherwise."""

    async def test_anonymous_caller_gets_401_without_the_path(
        self, client: AsyncClient, variant: _SeededVariant
    ) -> None:
        response = await client.get(variant.url)

        assert response.status_code == 401
        assert variant.file_path not in response.text

    async def test_member_gets_403_without_the_path(
        self,
        client: AsyncClient,
        variant: _SeededVariant,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=False)

        response = await client.get(variant.url)

        assert response.status_code == 403
        assert variant.file_path not in response.text

    async def test_admin_gets_the_variant_list(
        self,
        client: AsyncClient,
        variant: _SeededVariant,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login(client, seed_user_with_profile, is_admin=True)

        response = await client.get(variant.url)

        assert response.status_code == 200
        [file] = response.json()["data"]
        assert file["file_path"] == variant.file_path
        assert file["resolution"] == "1080p"
        assert file["is_primary"] is True
