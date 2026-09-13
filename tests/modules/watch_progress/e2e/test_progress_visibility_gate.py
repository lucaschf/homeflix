"""End-to-end tests for the watch progress visibility gate (ADR-035).

Drives the real progress routes over the in-process ASGI transport
against an in-memory database.

``Profile`` has no maturity limit yet, so the production
``ProfileViewingPolicyAdapter`` can only build library-only policies.
The first class overrides the watch progress container's
``profile_viewing_policy`` provider with a policy that carries a limit —
the only way to see the age axis end to end. The second class runs
without the override, so it also proves the composition root hands the
container an Identity UoW factory.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
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
from src.modules.watch_progress.application.ports import ProfileViewingPolicyPort
from src.modules.watch_progress.domain.value_objects import ProgressId
from src.modules.watch_progress.infrastructure.persistence.models import WatchProgressModel
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.e2e.conftest import SeededUser

PROGRESS_PATH = "/api/v1/progress"
CONTINUE_WATCHING_PATH = "/api/v1/progress/continue-watching"

_LIBRARY_ID = "lib_progressgate"
_OTHER_LIBRARY_ID = "lib_otherlib0001"
_LIMIT = 12
_MISSING_MOVIE_ID = "mov_missing00000"

type _Login = Callable[..., Awaitable[SeededUser]]


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


@pytest.fixture(scope="function")
async def limited_profile(app: FastAPI) -> AsyncGenerator[None, None]:
    """Resolve every profile to one library with a maturity limit of 12."""
    provider = app.state.container.watch_progress.profile_viewing_policy
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


def _certification(age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS,
        label=ContentRating(str(age)),
        minimum_age=AgeRating(age),
    )


async def _seed_movie(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    title: str,
    age: int,
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
        certification=_certification(age),
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)


async def _seed_series(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    title: str,
    age: int,
) -> str:
    series_id = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=1,
        episode_number=1,
        title=Title(f"{title} Pilot"),
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
        certification=_certification(age),
    )
    async with session_factory() as session:
        saved = await SQLAlchemySeriesRepository(session).save(series)
        await session.commit()
    return str(saved.id)


async def _seed_progress(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    profile_id: str,
    media_id: str,
    last_watched_at: datetime,
    media_type: str = "movie",
) -> None:
    """Insert a progress row directly, as one recorded before a restriction would be."""
    async with session_factory() as session:
        session.add(
            WatchProgressModel(
                external_id=ProgressId.generate().value,
                profile_id=profile_id,
                media_id=media_id,
                media_type=media_type,
                position_seconds=600,
                duration_seconds=7200,
                status="in_progress",
                last_watched_at=last_watched_at,
            )
        )
        await session.commit()


async def _live_progress_media_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> set[str]:
    async with session_factory() as session:
        result = await session.execute(
            select(WatchProgressModel.media_id).where(WatchProgressModel.deleted_at.is_(None))
        )
        return set(result.scalars())


def _save_body(media_id: str, media_type: str = "movie") -> dict[str, object]:
    return {
        "media_id": media_id,
        "media_type": media_type,
        "position_seconds": 600,
        "duration_seconds": 7200,
    }


def _assert_not_found_like_missing(
    response: Response, missing: Response, *, requested_id: str
) -> None:
    """The refusal must be indistinguishable from a title that does not exist.

    The only difference allowed is the id each request itself sent.
    """
    assert missing.status_code == 404
    assert response.status_code == 404
    body, missing_body = response.json(), missing.json()
    assert body.keys() == missing_body.keys()
    assert body["type"] == missing_body["type"]
    assert body["code"] == missing_body["code"]
    assert body.get("details") == missing_body.get("details")
    assert body["message"].replace(requested_id, "<id>") == missing_body["message"].replace(
        _MISSING_MOVIE_ID, "<id>"
    )


@pytest.mark.e2e
@pytest.mark.usefixtures("limited_profile")
class TestProgressGateWithMaturityLimit:
    """Progress routes under a policy with one library and a limit of 12."""

    async def test_put_above_limit_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        title = "Sixteen Plus Movie"
        movie_id = await _seed_movie(session_factory, title=title, age=16)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        restricted = await client.put(PROGRESS_PATH, json=_save_body(movie_id))
        missing = await client.put(PROGRESS_PATH, json=_save_body(_MISSING_MOVIE_ID))

        _assert_not_found_like_missing(restricted, missing, requested_id=movie_id)
        assert title not in restricted.text
        assert await _live_progress_media_ids(session_factory) == set()

    async def test_put_other_library_is_404_like_a_missing_movie(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(
            session_factory, title="Other Shelf Movie", age=10, library_id=_OTHER_LIBRARY_ID
        )
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        restricted = await client.put(PROGRESS_PATH, json=_save_body(movie_id))
        missing = await client.put(PROGRESS_PATH, json=_save_body(_MISSING_MOVIE_ID))

        _assert_not_found_like_missing(restricted, missing, requested_id=movie_id)
        assert await _live_progress_media_ids(session_factory) == set()

    async def test_put_episode_of_series_above_limit_is_404(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        series_id = await _seed_series(session_factory, title="Sixteen Plus Show", age=16)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.put(
            PROGRESS_PATH, json=_save_body(f"epi_{series_id}_1_1", media_type="episode")
        )

        assert response.status_code == 404
        assert "Sixteen Plus Show" not in response.text
        assert await _live_progress_media_ids(session_factory) == set()

    async def test_put_within_limit_returns_200(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, title="Ten Plus Movie", age=10)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.put(PROGRESS_PATH, json=_save_body(movie_id))

        assert response.status_code == 200
        assert response.json()["data"]["media_id"] == movie_id

    async def test_get_row_above_limit_reads_as_absent(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, title="Sixteen Plus Movie", age=16)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=movie_id,
            last_watched_at=datetime.now(UTC),
        )

        response = await client.get(f"{PROGRESS_PATH}/{movie_id}")

        assert response.status_code == 200
        assert response.json()["data"] is None

    async def test_continue_watching_hides_title_and_refills_the_window(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        hidden_title = "Sixteen Plus Movie"
        visible_title = "Ten Plus Movie"
        hidden_id = await _seed_movie(session_factory, title=hidden_title, age=16)
        visible_id = await _seed_movie(session_factory, title=visible_title, age=10)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        now = datetime.now(UTC)
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=visible_id,
            last_watched_at=now - timedelta(hours=1),
        )
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=hidden_id,
            last_watched_at=now,
        )

        response = await client.get(CONTINUE_WATCHING_PATH, params={"limit": 1})

        assert response.status_code == 200
        assert hidden_title not in response.text
        assert hidden_id not in response.text
        assert [item["media_id"] for item in response.json()["data"]] == [visible_id]
        assert response.json()["data"][0]["title"] == visible_title

    async def test_continue_watching_answers_missing_and_hidden_titles_alike(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """With ``limit=1`` the newest row must not reveal whether its title exists."""
        hidden_id = await _seed_movie(session_factory, title="Sixteen Plus Movie", age=16)
        visible_id = await _seed_movie(session_factory, title="Ten Plus Movie", age=10)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        now = datetime.now(UTC)
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=visible_id,
            last_watched_at=now - timedelta(hours=1),
        )

        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=_MISSING_MOVIE_ID,
            last_watched_at=now,
        )
        behind_missing = await client.get(CONTINUE_WATCHING_PATH, params={"limit": 1})
        cleared = await client.delete(f"{PROGRESS_PATH}/{_MISSING_MOVIE_ID}")
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=hidden_id,
            last_watched_at=now,
        )
        behind_hidden = await client.get(CONTINUE_WATCHING_PATH, params={"limit": 1})

        assert cleared.status_code == 204
        assert behind_missing.status_code == behind_hidden.status_code == 200
        assert behind_missing.json()["data"] == behind_hidden.json()["data"]
        assert [item["media_id"] for item in behind_hidden.json()["data"]] == [visible_id]

    async def test_delete_row_above_limit_returns_204_and_removes_it(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, title="Sixteen Plus Movie", age=16)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=movie_id,
            last_watched_at=datetime.now(UTC),
        )

        response = await client.delete(f"{PROGRESS_PATH}/{movie_id}")

        assert response.status_code == 204
        assert await _live_progress_media_ids(session_factory) == set()

    async def test_no_progress_route_answers_401_for_restricted_titles(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """An unexpected 401 logs the web client out, so a refusal must never be one."""
        movie_id = await _seed_movie(session_factory, title="Sixteen Plus Movie", age=16)
        series_id = await _seed_series(session_factory, title="Sixteen Plus Show", age=16)
        user = await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        await _seed_progress(
            session_factory,
            profile_id=user.profile_external_id,
            media_id=movie_id,
            last_watched_at=datetime.now(UTC),
        )

        responses = [
            await client.put(PROGRESS_PATH, json=_save_body(movie_id)),
            await client.put(PROGRESS_PATH, json=_save_body(_MISSING_MOVIE_ID)),
            await client.get(f"{PROGRESS_PATH}/{movie_id}"),
            await client.get(CONTINUE_WATCHING_PATH),
            await client.delete(f"{PROGRESS_PATH}/{movie_id}"),
            await client.delete(f"{PROGRESS_PATH}/series/{series_id}"),
        ]

        assert [r.status_code for r in responses] == [404, 404, 200, 200, 204, 204]


@pytest.mark.e2e
class TestProgressGateWithProductionPolicy:
    """Without an override the profile's own ACL decides, through the real adapter."""

    async def test_put_within_acl_returns_200(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, title="Shelf Movie", age=16)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.put(PROGRESS_PATH, json=_save_body(movie_id))

        assert response.status_code == 200
        assert response.json()["data"]["media_id"] == movie_id
        assert await _live_progress_media_ids(session_factory) == {movie_id}

    async def test_put_outside_acl_returns_404(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(
            session_factory, title="Other Shelf Movie", age=10, library_id=_OTHER_LIBRARY_ID
        )
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.put(PROGRESS_PATH, json=_save_body(movie_id))

        assert response.status_code == 404
        assert await _live_progress_media_ids(session_factory) == set()

    async def test_continue_watching_lists_title_within_acl(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, title="Shelf Movie", age=16)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])
        assert (await client.put(PROGRESS_PATH, json=_save_body(movie_id))).status_code == 200

        response = await client.get(CONTINUE_WATCHING_PATH)

        assert response.status_code == 200
        assert [item["media_id"] for item in response.json()["data"]] == [movie_id]
