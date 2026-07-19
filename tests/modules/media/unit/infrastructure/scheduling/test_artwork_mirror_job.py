"""Unit tests for :class:`ArtworkMirrorJob` (ADR-029).

Drives the job with in-memory fakes for the UoW/repositories, the
downloader and the storage, so the orchestration is verified without a
DB or network: which references get mirrored, which are left as-is, that
a download failure or a non-image response keeps the remote URL, and the
per-kind budget split.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.building_blocks.infrastructure.errors import GatewayUnavailableException
from src.infrastructure.scheduling.artwork_mirror_job import ArtworkMirrorJob
from src.modules.media.application.ports.artwork_downloader_port import DownloadedImage
from src.modules.media.domain.repositories.movie_repository import RemoteArtworkRow
from src.modules.media.domain.value_objects import ArtworkColumns, ImageUrl
from src.modules.settings.domain.value_objects import ArtworkMirrorConfig

REMOTE = "https://image.tmdb.org/t/p/original/x.jpg"
REMOTE_B = "https://image.tmdb.org/t/p/original/b.jpg"
LOCAL = "/api/v1/artwork/deadbeef.jpg"
MOVIE_ID = "mov_abc123def456"
SERIES_ID = "ser_abc123def456"


def _row(media_id: str, *, poster=None, backdrop=None, logo=None) -> RemoteArtworkRow:
    return RemoteArtworkRow(
        media_id=media_id,
        artwork=ArtworkColumns(
            poster=ImageUrl(poster) if poster else None,
            backdrop=ImageUrl(backdrop) if backdrop else None,
            logo=ImageUrl(logo) if logo else None,
        ),
    )


class _FakeRepo:
    def __init__(self, rows: list[RemoteArtworkRow]) -> None:
        self._rows = rows
        self.updates: list[tuple[str, ArtworkColumns]] = []

    async def find_with_remote_artwork(self, limit: int) -> list[RemoteArtworkRow]:
        return self._rows[:limit]


class _FakeMovieRepo(_FakeRepo):
    async def update_movie_artwork(self, movie_id, artwork: ArtworkColumns) -> None:
        self.updates.append((str(movie_id), artwork))


class _FakeSeriesRepo(_FakeRepo):
    async def update_series_artwork(self, series_id, artwork: ArtworkColumns) -> None:
        self.updates.append((str(series_id), artwork))


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
    def __init__(
        self,
        *,
        fail_urls: set[str] = frozenset(),
        nonimage_urls: set[str] = frozenset(),
    ) -> None:
        self._fail_urls = fail_urls
        self._nonimage_urls = nonimage_urls
        self.fetched: list[str] = []

    async def fetch(self, url: str, *, max_bytes: int) -> DownloadedImage:
        self.fetched.append(url)
        if url in self._fail_urls:
            raise GatewayUnavailableException(message="down", gateway_name="artwork-cdn")
        content_type = "text/html" if url in self._nonimage_urls else "image/jpeg"
        return DownloadedImage(content=b"image-bytes", content_type=content_type)


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
    nonimage_urls: set[str] = frozenset(),
) -> _Harness:
    movies = _FakeMovieRepo(list(movie_rows or []))
    series = _FakeSeriesRepo(list(series_rows or []))
    uow = _FakeUow(movies=movies, series=series)
    downloader = _FakeDownloader(fail_urls=fail_urls, nonimage_urls=nonimage_urls)
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
        h = _make(movie_rows=[_row(MOVIE_ID, poster=REMOTE, backdrop=LOCAL, logo=None)])

        await h.job.run()

        assert len(h.movies.updates) == 1
        media_id, cols = h.movies.updates[0]
        assert media_id == MOVIE_ID
        assert cols.poster.value.startswith("/api/v1/artwork/")  # mirrored
        assert cols.backdrop == ImageUrl(LOCAL)  # already local — untouched
        assert cols.logo is None  # absent — untouched
        assert h.storage.saved  # one object stored

    async def test_should_keep_remote_url_when_download_fails(self) -> None:
        h = _make(movie_rows=[_row(MOVIE_ID, poster=REMOTE)], fail_urls={REMOTE})

        await h.job.run()

        # Nothing changed → no update issued, remote URL stays for a retry.
        assert h.movies.updates == []
        assert h.storage.saved == []

    async def test_should_keep_remote_url_when_response_is_not_an_image(self) -> None:
        # A 200 serving HTML (rate-limit page) must never overwrite the
        # authoritative remote URL with a broken "artwork".
        h = _make(movie_rows=[_row(MOVIE_ID, poster=REMOTE)], nonimage_urls={REMOTE})

        await h.job.run()

        assert h.movies.updates == []
        assert h.storage.saved == []

    async def test_should_persist_partial_when_one_field_fails(self) -> None:
        # Two remote fields, one download fails: the winner is mirrored,
        # the loser keeps its remote URL, and the title is still updated.
        h = _make(
            movie_rows=[_row(MOVIE_ID, poster=REMOTE, backdrop=REMOTE_B)],
            fail_urls={REMOTE_B},
        )

        await h.job.run()

        assert len(h.movies.updates) == 1
        _, cols = h.movies.updates[0]
        assert cols.poster.value.startswith("/api/v1/artwork/")
        assert cols.backdrop == ImageUrl(REMOTE_B)  # failed → kept remote
        assert len(h.storage.saved) == 1

    async def test_should_mirror_series_too(self) -> None:
        h = _make(series_rows=[_row(SERIES_ID, poster=REMOTE, backdrop=REMOTE)])

        await h.job.run()

        assert len(h.series.updates) == 1
        _, cols = h.series.updates[0]
        assert cols.poster.value.startswith("/api/v1/artwork/")
        assert cols.backdrop.value.startswith("/api/v1/artwork/")

    async def test_should_split_budget_between_kinds(self) -> None:
        # batch_size 1 → the single slot goes to the movie; series is not
        # fetched this tick.
        h = _make(
            movie_rows=[_row(MOVIE_ID, poster=REMOTE)],
            series_rows=[_row(SERIES_ID, poster=REMOTE)],
            config=ArtworkMirrorConfig(batch_size=1),
        )

        await h.job.run()

        assert len(h.movies.updates) == 1
        assert h.series.updates == []
