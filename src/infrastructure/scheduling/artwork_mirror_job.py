"""Periodic mirror of provider artwork into local storage (ADR-029).

Finds movies and series whose poster/backdrop/logo is still a remote
TMDB URL, downloads the bytes, persists them via
:class:`ArtworkStoragePort`, and swaps the column for the local
``/api/v1/artwork/{key}`` reference. The catalog then serves art from
storage the deployment controls, tolerating TMDB removal, rate limits,
CDN outages, and offline use.

Each tick processes at most ``batch_size`` titles split between movies
and series. Network I/O never happens while a DB session is held: rows
are fetched in one short UoW, mirrored without a session, and the
column update runs in a fresh per-title UoW. A download failure is
logged and leaves the remote URL untouched (graceful fallback), so a
flaky provider only defers mirroring to a later tick.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.building_blocks.infrastructure.errors import GatewayException
from src.config.logging import get_logger
from src.modules.media.domain.value_objects import ArtworkKey
from src.modules.media.domain.value_objects.artwork_key import (
    SUPPORTED_ARTWORK_CONTENT_TYPES,
)
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.modules.media.application.ports.artwork_downloader_port import (
        ArtworkDownloaderPort,
    )
    from src.modules.media.application.ports.artwork_storage_port import ArtworkStoragePort
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.repositories.movie_repository import RemoteArtworkRow
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()

# The top-level artwork columns this job mirrors. Season posters, episode
# stills, localized art and cast photos are out of scope here (PR 3).
_ARTWORK_FIELDS = ("poster_path", "backdrop_path", "logo_path")


class ArtworkMirrorJob:
    """Download still-remote artwork and replace it with local references.

    Args:
        media_uow_factory: Builds fresh media UoWs. Fetch and each
            per-title update open their own UoW so a single failure
            rolls back only that title.
        runtime_settings: Snapshot facade for :class:`ArtworkMirrorConfig`
            (batch size + max download size), read per ``run()`` so admin
            edits apply on the next tick (ADR-013).
        downloader: Fetches the remote image bytes.
        storage: Persists the bytes and returns the served URL.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        runtime_settings: RuntimeSettings,
        downloader: ArtworkDownloaderPort,
        storage: ArtworkStoragePort,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._runtime_settings = runtime_settings
        self._downloader = downloader
        self._storage = storage

    async def run(self) -> None:
        """Mirror one batch of titles with still-remote artwork.

        Splits the per-tick budget between movies and series: movies
        first, remaining slots go to series. Logs how many titles were
        updated and how many individual images were mirrored vs. failed.
        """
        config = await self._runtime_settings.artwork_mirror()
        budget = config.batch_size

        movies = await self._fetch_movies(budget)
        movies_updated, movies_mirrored, movies_failed = await self._process(
            movies, is_movie=True, max_bytes=config.max_bytes
        )
        budget -= len(movies)

        series_updated = series_mirrored = series_failed = 0
        if budget > 0:
            series = await self._fetch_series(budget)
            series_updated, series_mirrored, series_failed = await self._process(
                series, is_movie=False, max_bytes=config.max_bytes
            )

        if movies_mirrored or series_mirrored or movies_failed or series_failed:
            _logger.info(
                "[artwork-mirror] tick complete",
                movies_updated=movies_updated,
                movies_mirrored=movies_mirrored,
                movies_failed=movies_failed,
                series_updated=series_updated,
                series_mirrored=series_mirrored,
                series_failed=series_failed,
                batch_size=config.batch_size,
            )

    async def _fetch_movies(self, limit: int) -> Sequence[RemoteArtworkRow]:
        async with self._media_uow_factory() as uow:
            return await uow.movies.find_with_remote_artwork(limit)

    async def _fetch_series(self, limit: int) -> Sequence[RemoteArtworkRow]:
        async with self._media_uow_factory() as uow:
            return await uow.series.find_with_remote_artwork(limit)

    async def _process(
        self,
        rows: Sequence[RemoteArtworkRow],
        *,
        is_movie: bool,
        max_bytes: int,
    ) -> tuple[int, int, int]:
        """Mirror every row's artwork; return (titles_updated, mirrored, failed)."""
        titles_updated = 0
        mirrored = 0
        failed = 0
        for row in rows:
            values, hits, misses = await self._mirror_row(row, max_bytes)
            mirrored += hits
            failed += misses
            if hits:
                await self._persist(row.media_id, values, is_movie=is_movie)
                titles_updated += 1
        return titles_updated, mirrored, failed

    async def _mirror_row(
        self,
        row: RemoteArtworkRow,
        max_bytes: int,
    ) -> tuple[dict[str, str | None], int, int]:
        """Mirror each remote field of ``row``.

        Returns the final value for all three columns (local URL where a
        mirror succeeded, the original value otherwise) plus the count of
        successful and failed downloads.
        """
        values: dict[str, str | None] = {}
        hits = 0
        misses = 0
        for field in _ARTWORK_FIELDS:
            current = getattr(row, field)
            mirrored_url = await self._mirror_one(current, max_bytes)
            if mirrored_url is None:
                values[field] = current
                if _is_remote(current):
                    misses += 1  # was remote but the download failed
            else:
                values[field] = mirrored_url
                hits += 1
        return values, hits, misses

    async def _mirror_one(self, url: str | None, max_bytes: int) -> str | None:
        """Download + store one image; return its served URL, or None.

        None means "leave the column unchanged": the value was not a
        remote URL, the response was not a supported image type, or the
        download/store failed. Every non-mirror path keeps the original
        remote URL so a later tick can retry — a bad response never
        overwrites the authoritative provider URL.
        """
        if not _is_remote(url):
            return None
        assert url is not None  # narrowed by _is_remote
        try:
            image = await self._downloader.fetch(url, max_bytes=max_bytes)
            if not _is_supported_image(image.content_type):
                # A 200 serving HTML (rate-limit/geoblock page) or an
                # svg/unknown type must not be stored over the remote URL.
                _logger.warning(
                    "[artwork-mirror] non-image response; keeping remote URL",
                    url=url,
                    content_type=image.content_type,
                )
                return None
            key = ArtworkKey.for_content(
                image.content,
                content_type=image.content_type,
                source_url=url,
            )
            return await self._storage.save(
                content=image.content,
                content_type=image.content_type,
                key=str(key),
            )
        except GatewayException as exc:
            _logger.warning(
                "[artwork-mirror] download failed; keeping remote URL",
                url=url,
                error=str(exc),
            )
            return None
        except OSError as exc:
            _logger.warning(
                "[artwork-mirror] storage failed; keeping remote URL",
                url=url,
                error=str(exc),
            )
            return None

    async def _persist(
        self,
        media_id: str,
        values: dict[str, str | None],
        *,
        is_movie: bool,
    ) -> None:
        """Write the mirrored artwork columns in a fresh UoW.

        Writes all three columns from the fetch-time snapshot (mirrored
        where produced, original otherwise). This is a blind
        last-writer-wins update: a concurrent re-enrichment in the small
        fetch→persist window could be reverted, but the 30-min cadence
        and self-healing re-mirror on the next tick make that acceptable
        over guarding every column value in the WHERE clause.
        """
        async with self._media_uow_factory() as uow:
            if is_movie:
                await uow.movies.update_movie_artwork(
                    MovieId(media_id),
                    poster_path=values["poster_path"],
                    backdrop_path=values["backdrop_path"],
                    logo_path=values["logo_path"],
                )
            else:
                await uow.series.update_series_artwork(
                    SeriesId(media_id),
                    poster_path=values["poster_path"],
                    backdrop_path=values["backdrop_path"],
                    logo_path=values["logo_path"],
                )


def _is_remote(url: str | None) -> bool:
    """Whether ``url`` is a value the job should mirror (an http(s) URL)."""
    return bool(url) and url.startswith("http")  # type: ignore[union-attr]


def _is_supported_image(content_type: str | None) -> bool:
    """Whether a response content type is an artwork image we will store."""
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() in SUPPORTED_ARTWORK_CONTENT_TYPES


__all__ = ["ArtworkMirrorJob"]
