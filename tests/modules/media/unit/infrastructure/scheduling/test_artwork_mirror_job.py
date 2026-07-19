"""Unit tests for :class:`ArtworkMirrorJob` (ADR-029).

Drives the job with in-memory fakes for the UoW/repositories, the
downloader and the storage, so the orchestration is verified without a
DB or network: which fields get mirrored, which are left as-is, that a
download failure keeps the remote URL, and the movies/series budget
split.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.building_blocks.infrastructure.errors import GatewayUnavailableException
from src.infrastructure.scheduling.artwork_mirror_job import ArtworkMirrorJob
from src.modules.media.application.ports.artwork_downloader_port import DownloadedImage
from src.modules.media.domain.repositories.movie_repository import RemoteArtworkRow
from src.modules.settings.domain.value_objects import ArtworkMirrorConfig

REMOTE = "https://image.tmdb.org/t/p/original/x.jpg"
LOCAL = "/api/v1/artwork/deadbeef.jpg"


@dataclass
class _Update:
    media_id: str
    poster_path: str | None
    backdrop_path: str | None
    logo_path: str | None


class _FakeRepo:
    def __init__(self, rows: list[RemoteArtworkRow]) -> None:
        self._rows = rows
        self.updates: list[_Update] = []

    async def find_with_remote_artwork(self, limit: int) -> list[RemoteArtworkRow]:
        return self._rows[:limit]

    async def _record(self, media_id: str, poster_path, backdrop_path, logo_path) -> None:
        self.updates.append(_Update(media_id, poster_path, backdrop_path, logo_path))


class _FakeMovieRepo(_FakeRepo):
    async def update_movie_artwork(
        self, movie_id, *, poster_path, backdrop_path, logo_path
    ) -> None:
        await self._record(str(movie_id), poster_path, backdrop_path, logo_path)


class _FakeSeriesRepo(_FakeRepo):
    async def update_series_artwork(
        self, series_id, *, poster_path, backdrop_path, logo_path
    ) -> None:
        await self._record(str(series_id), poster_path, backdrop_path, logo_path)


@dataclass
class _FakeUow:
    movies: _FakeMovieRepo
    series: _FakeSeriesRepo

    async def __aenter__(self) -> _FakeUow:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeUowFactory:
    def __init__(self, uow: _FakeUow) -> None:
        self._uow = uow

    def __call__(self) -> _FakeUow:
        return self._uow


class _FakeRuntimeSettings:
    def __init__(self, config: ArtworkMirrorConfig) -> None:
        self._config = config

    async def artwork_mirror(self) -> ArtworkMirrorConfig:
        return self._config


class _FakeDownloader:
    def __init__(self, *, fail_urls: set[str] = frozenset()) -> None:
        self._fail_urls = fail_urls
        self.fetched: list[str] = []

    async def fetch(self, url: str, *, max_bytes: int) -> DownloadedImage:
        self.fetched.append(url)
        if url in self._fail_urls:
            raise GatewayUnavailableException(message="down", gateway_name="artwork-cdn")
        return DownloadedImage(content=b"image-bytes", content_type="image/jpeg")


class _FakeStorage:
    def __init__(self) -> None:
        self.saved: list[str] = []

    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        self.saved.append(key)
        return f"/api/v1/artwork/{key}"


@dataclass
class _Harness:
    job: ArtworkMirrorJob
    movies: _FakeMovieRepo
    series: _FakeSeriesRepo
    downloader: _FakeDownloader
    storage: _FakeStorage


def _make(
    *,
    movie_rows: list[RemoteArtworkRow] | None = None,
    series_rows: list[RemoteArtworkRow] | None = None,
    config: ArtworkMirrorConfig | None = None,
    fail_urls: set[str] = frozenset(),
) -> _Harness:
    movies = _FakeMovieRepo(list(movie_rows or []))
    series = _FakeSeriesRepo(list(series_rows or []))
    uow = _FakeUow(movies=movies, series=series)
    downloader = _FakeDownloader(fail_urls=fail_urls)
    storage = _FakeStorage()
    job = ArtworkMirrorJob(
        media_uow_factory=_FakeUowFactory(uow),
        runtime_settings=_FakeRuntimeSettings(config or ArtworkMirrorConfig()),
        downloader=downloader,
        storage=storage,
    )
    return _Harness(job=job, movies=movies, series=series, downloader=downloader, storage=storage)


class TestRun:
    async def test_should_mirror_remote_fields_and_leave_others(self) -> None:
        h = _make(
            movie_rows=[
                RemoteArtworkRow(
                    media_id="mov_abc123def456",
                    poster_path=REMOTE,
                    backdrop_path=LOCAL,  # already local — untouched
                    logo_path=None,  # absent — untouched
                )
            ]
        )

        await h.job.run()

        assert len(h.movies.updates) == 1
        update = h.movies.updates[0]
        assert update.media_id == "mov_abc123def456"
        assert update.poster_path.startswith("/api/v1/artwork/")
        assert update.backdrop_path == LOCAL
        assert update.logo_path is None
        assert h.storage.saved  # one object stored

    async def test_should_keep_remote_url_when_download_fails(self) -> None:
        h = _make(
            movie_rows=[
                RemoteArtworkRow(
                    media_id="mov_abc123def456",
                    poster_path=REMOTE,
                    backdrop_path=None,
                    logo_path=None,
                )
            ],
            fail_urls={REMOTE},
        )

        await h.job.run()

        # Nothing changed → no update issued, remote URL stays for a retry.
        assert h.movies.updates == []
        assert h.storage.saved == []

    async def test_should_mirror_series_too(self) -> None:
        h = _make(
            series_rows=[
                RemoteArtworkRow(
                    media_id="ser_abc123def456",
                    poster_path=REMOTE,
                    backdrop_path=REMOTE,
                    logo_path=None,
                )
            ]
        )

        await h.job.run()

        assert len(h.series.updates) == 1
        update = h.series.updates[0]
        assert update.poster_path.startswith("/api/v1/artwork/")
        assert update.backdrop_path.startswith("/api/v1/artwork/")

    async def test_should_split_budget_between_movies_and_series(self) -> None:
        # batch_size 1 → the single slot goes to the movie; series is not
        # fetched this tick.
        h = _make(
            movie_rows=[
                RemoteArtworkRow(
                    media_id="mov_abc123def456", poster_path=REMOTE, backdrop_path=None, logo_path=None
                )
            ],
            series_rows=[
                RemoteArtworkRow(
                    media_id="ser_abc123def456", poster_path=REMOTE, backdrop_path=None, logo_path=None
                )
            ],
            config=ArtworkMirrorConfig(batch_size=1),
        )

        await h.job.run()

        assert len(h.movies.updates) == 1
        assert h.series.updates == []
