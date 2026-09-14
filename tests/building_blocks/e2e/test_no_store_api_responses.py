"""End-to-end tests for the JSON ``no-store`` cache policy (ADR-035).

Drives the app built by ``create_app`` over the in-process ASGI
transport, so the assertions prove the middleware is registered in the
composition root — not only that the middleware works on a toy app.

Covers the profile-filtered reads (catalog list and detail, Continue
Watching, watchlist, custom lists), the JSON error envelopes and the two
non-JSON surfaces that set their own caching: the artwork proxy and HLS
file delivery. The envelopes come from both places Starlette turns
exceptions into responses — the route itself (403 on the maturity axis
and 404 from a use case, 401 from the session guard) and
``ExceptionMiddleware`` (404 on an unmatched path, 405) — so a
middleware mounted inside the latter fails here. The 403 test overrides
the media container's ``profile_viewing_policy``, as in the media detail
gate e2e, to pin the header independently of seeded profile data.
Artwork storage and the HLS cache are swapped for in-memory fakes; both
routes are public, so they need no login.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
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
from src.modules.metadata.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)
from src.modules.streaming.application.ports.hls_playlist_port import (
    HlsCacheStats,
    HlsPlaylistPort,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.media_probe.media_probe_port import ProbeResult
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.collections.e2e.conftest import SeededUser

_LIBRARY_ID = "lib_nostore00001"
_MISSING_MOVIE_ID = "mov_missing00000"
_PATH_HASH = "0123456789abcdef"
_LIMIT = 12

type _Login = Callable[..., Awaitable[SeededUser]]


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


class _FakeArtworkStorage(ArtworkStoragePort):
    """In-memory artwork storage keyed by object key."""

    def __init__(self) -> None:
        self._objects: dict[str, StoredArtwork] = {}

    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        self._objects[key] = StoredArtwork(content=content, content_type=content_type)
        return f"/api/v1/artwork/{key}"

    async def open(self, key: str) -> StoredArtwork | None:
        return self._objects.get(key)

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


class _FakeHlsCache(HlsPlaylistPort):
    """HLS cache backed by a plain directory; only file lookup is exercised."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def ensure_playlist(self, file_path: str, start: int = 0, end: int | None = None) -> str:
        raise NotImplementedError

    def get_master_playlist(self, path_hash: str) -> str | None:
        raise NotImplementedError

    def get_file_by_hash(self, path_hash: str, relative_path: str) -> Path | None:
        candidate = self._root / path_hash / relative_path
        return candidate if candidate.is_file() else None

    def wait_for_subtitle(self, path_hash: str, sub_index: int, timeout: float) -> bool:
        return True

    def probe_tracks(self, file_path: str) -> ProbeResult:
        raise NotImplementedError

    def clear_cache(self, file_path: str | None) -> None:
        raise NotImplementedError

    def get_cache_stats(self) -> HlsCacheStats:
        raise NotImplementedError


@pytest.fixture(scope="function")
async def limited_profile(app: FastAPI) -> AsyncGenerator[None, None]:
    """Resolve every profile to the seeded library with a maturity limit of 12."""
    provider = app.state.container.media.profile_viewing_policy
    provider.override(
        providers.Object(
            _FixedViewingPolicy(
                ViewingPolicy(allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(_LIMIT))
            )
        )
    )
    yield
    provider.reset_last_overriding()


@pytest.fixture(scope="function")
async def artwork_storage(app: FastAPI) -> AsyncGenerator[_FakeArtworkStorage, None]:
    """Swap the artwork storage for an in-memory fake."""
    fake = _FakeArtworkStorage()
    provider = app.state.container.metadata.artwork_storage
    provider.override(providers.Object(fake))
    yield fake
    provider.reset_override()


@pytest.fixture(scope="function")
async def hls_cache_root(app: FastAPI, tmp_path: Path) -> AsyncGenerator[Path, None]:
    """Serve HLS files from ``tmp_path/<path_hash>/`` instead of the ffmpeg cache."""
    provider = app.state.container.streaming.hls_service
    provider.override(providers.Object(_FakeHlsCache(tmp_path)))
    yield tmp_path / _PATH_HASH
    provider.reset_override()


async def _seed_movie(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    minimum_age: int = 10,
) -> str:
    movie = Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title("Cached Nowhere"),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{_LIBRARY_ID}/cached-nowhere.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        certification=Certification(
            system=RatingSystem.BR_DEJUS,
            label=ContentRating(str(minimum_age)),
            minimum_age=AgeRating(minimum_age),
        ),
    )
    async with session_factory() as session:
        saved = await SQLAlchemyMovieRepository(session).save(movie)
        await session.commit()
    return str(saved.id)


def _assert_json_no_store(response: Response, *, status_code: int) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.e2e
class TestProfileFilteredReads:
    """Reads filtered by the active profile are never stored by a cache."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/movies",
            "/api/v1/movies/{movie_id}",
            "/api/v1/progress/continue-watching",
            "/api/v1/watchlist",
            "/api/v1/custom-lists",
        ],
    )
    async def test_should_send_no_store(
        self,
        path: str,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.get(path.format(movie_id=movie_id))

        _assert_json_no_store(response, status_code=200)


@pytest.mark.e2e
class TestErrorEnvelopes:
    """Error envelopes from the global handlers carry ``no-store`` too."""

    @pytest.mark.usefixtures("limited_profile")
    async def test_maturity_forbidden_sends_no_store(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        movie_id = await _seed_movie(session_factory, minimum_age=16)
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.get(f"/api/v1/movies/{movie_id}")

        _assert_json_no_store(response, status_code=403)
        assert response.json()["code"] == "CONTENT_RESTRICTED_BY_MATURITY"

    async def test_not_found_from_use_case_sends_no_store(
        self,
        client: AsyncClient,
        login_with_active_profile: _Login,
    ) -> None:
        await login_with_active_profile(allowed_library_ids=[_LIBRARY_ID])

        response = await client.get(f"/api/v1/movies/{_MISSING_MOVIE_ID}")

        _assert_json_no_store(response, status_code=404)

    async def test_unauthorized_without_session_sends_no_store(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/api/v1/watchlist")

        _assert_json_no_store(response, status_code=401)

    async def test_unmatched_path_sends_no_store(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/api/v1/no-such-resource")

        _assert_json_no_store(response, status_code=404)

    async def test_method_not_allowed_sends_no_store(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.delete("/health")

        _assert_json_no_store(response, status_code=405)
        assert response.headers["allow"] == "GET"


@pytest.mark.e2e
class TestNonJsonCaching:
    """Artwork and HLS keep the caching headers their routes set."""

    async def test_artwork_stays_immutable(
        self,
        client: AsyncClient,
        artwork_storage: _FakeArtworkStorage,
    ) -> None:
        await artwork_storage.save(content=b"poster", content_type="image/jpeg", key="ab12.jpg")

        response = await client.get("/api/v1/artwork/ab12.jpg")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    async def test_hls_playlist_stays_no_cache(
        self,
        client: AsyncClient,
        hls_cache_root: Path,
    ) -> None:
        playlist = hls_cache_root / "video" / "index.m3u8"
        playlist.parent.mkdir(parents=True)
        playlist.write_text("#EXTM3U\nsegment_0000.ts\n", encoding="utf-8")

        response = await client.get(f"/api/v1/stream/hls/{_PATH_HASH}/video/index.m3u8")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.apple.mpegurl"
        assert response.headers["cache-control"] == "no-cache"

    async def test_hls_segment_has_no_cache_control(
        self,
        client: AsyncClient,
        hls_cache_root: Path,
    ) -> None:
        segment = hls_cache_root / "video" / "segment_0000.ts"
        segment.parent.mkdir(parents=True)
        segment.write_bytes(b"\x47" * 188)

        response = await client.get(f"/api/v1/stream/hls/{_PATH_HASH}/video/segment_0000.ts")

        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp2t"
        assert response.content == b"\x47" * 188
        assert "cache-control" not in response.headers
