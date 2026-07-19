"""Periodic mirror of provider artwork into local storage (ADR-029).

Finds movies and series whose poster/backdrop/logo is still a remote
TMDB URL, downloads the bytes, persists them via
:class:`ArtworkStoragePort`, and swaps the column for the local
``/api/v1/artwork/{key}`` reference. The catalog then serves art from
storage the deployment controls, tolerating TMDB removal, rate limits,
CDN outages, and offline use.

Each tick processes at most ``batch_size`` titles split between the
title kinds. Network I/O never happens while a DB session is held: rows
are fetched in one short UoW, mirrored without a session, and the column
update runs in a fresh per-title UoW. A download failure (or a non-image
response) is logged and leaves the remote URL untouched (graceful
fallback), so a flaky provider only defers mirroring to a later tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.building_blocks.infrastructure.errors import GatewayException
from src.config.logging import get_logger
from src.modules.media.domain.value_objects import ArtworkColumns, ArtworkKey
from src.modules.media.domain.value_objects.artwork_key import (
    SUPPORTED_ARTWORK_CONTENT_TYPES,
)
from src.shared_kernel.value_objects.image_url import ImageUrl
from src.shared_kernel.value_objects.media_id import MovieId, SeasonId, SeriesId

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from src.modules.media.application.ports.artwork_downloader_port import (
        ArtworkDownloaderPort,
    )
    from src.modules.media.application.ports.artwork_storage_port import ArtworkStoragePort
    from src.modules.media.application.unit_of_work import (
        MediaUnitOfWork,
        MediaUnitOfWorkFactory,
    )
    from src.modules.media.domain.repositories.movie_repository import RemoteArtworkRow
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()


@dataclass(frozen=True)
class _Kind:
    """One artwork-bearing title kind the job mirrors (movie / series).

    Bundles how to find candidates and how to write them back, so the
    job loops over kinds instead of branching on a boolean flag. Adding
    season/episode art later is a new ``_Kind``, not a new ``if``.
    """

    label: str
    find: Callable[[MediaUnitOfWork, int], Awaitable[Sequence[RemoteArtworkRow]]]
    update: Callable[[MediaUnitOfWork, str, ArtworkColumns], Awaitable[None]]


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
        self._kinds: tuple[_Kind, ...] = (
            _Kind(
                label="movies",
                find=lambda uow, limit: uow.movies.find_with_remote_artwork(limit),
                update=lambda uow, media_id, cols: uow.movies.update_movie_artwork(
                    MovieId(media_id), cols
                ),
            ),
            _Kind(
                label="series",
                find=lambda uow, limit: uow.series.find_with_remote_artwork(limit),
                update=lambda uow, media_id, cols: uow.series.update_series_artwork(
                    SeriesId(media_id), cols
                ),
            ),
            _Kind(
                label="seasons",
                find=lambda uow, limit: uow.series.find_seasons_with_remote_poster(limit),
                update=lambda uow, media_id, cols: uow.series.update_season_artwork(
                    SeasonId(media_id), cols
                ),
            ),
        )

    async def run(self) -> None:
        """Mirror one batch of titles with still-remote artwork.

        Splits the per-tick budget across the title kinds in order, and
        logs how many titles were updated and how many images were
        mirrored vs. left remote per kind.
        """
        config = await self._runtime_settings.artwork_mirror()
        budget = config.batch_size
        stats: dict[str, int] = {}
        active = False
        for kind in self._kinds:
            if budget <= 0:
                break
            rows = await self._fetch(kind, budget)
            budget -= len(rows)
            updated, mirrored, failed = await self._process(kind, rows, config.max_bytes)
            stats[f"{kind.label}_updated"] = updated
            stats[f"{kind.label}_mirrored"] = mirrored
            stats[f"{kind.label}_failed"] = failed
            active = active or bool(mirrored or failed)

        if active:
            _logger.info(
                "[artwork-mirror] tick complete",
                batch_size=config.batch_size,
                **stats,
            )

    async def _fetch(self, kind: _Kind, limit: int) -> Sequence[RemoteArtworkRow]:
        async with self._media_uow_factory() as uow:
            return await kind.find(uow, limit)

    async def _process(
        self,
        kind: _Kind,
        rows: Sequence[RemoteArtworkRow],
        max_bytes: int,
    ) -> tuple[int, int, int]:
        """Mirror every row; return (titles_updated, mirrored, failed)."""
        updated = 0
        mirrored = 0
        failed = 0
        for row in rows:
            columns, hits, misses = await self._mirror_row(row, max_bytes)
            mirrored += hits
            failed += misses
            if hits:
                await self._persist(kind, row.media_id, columns)
                updated += 1
        return updated, mirrored, failed

    async def _persist(self, kind: _Kind, media_id: str, artwork: ArtworkColumns) -> None:
        """Write the mirrored artwork columns in a fresh UoW.

        A blind last-writer-wins column update from the fetch-time
        snapshot: a concurrent re-enrichment in the small fetch→persist
        window could be reverted, but the 30-min cadence and self-healing
        re-mirror on the next tick make that acceptable over guarding
        every column value in the WHERE clause.
        """
        async with self._media_uow_factory() as uow:
            await kind.update(uow, media_id, artwork)

    async def _mirror_row(
        self,
        row: RemoteArtworkRow,
        max_bytes: int,
    ) -> tuple[ArtworkColumns, int, int]:
        """Mirror each remote reference of ``row``.

        Returns the final columns (local reference where a mirror
        succeeded, the original value otherwise) plus the count of
        successful and failed mirrors.
        """
        poster, hp, mp = await self._mirror_field(row.artwork.poster, max_bytes)
        backdrop, hb, mb = await self._mirror_field(row.artwork.backdrop, max_bytes)
        logo, hl, ml = await self._mirror_field(row.artwork.logo, max_bytes)
        return (
            ArtworkColumns(poster=poster, backdrop=backdrop, logo=logo),
            hp + hb + hl,
            mp + mb + ml,
        )

    async def _mirror_field(
        self,
        current: ImageUrl | None,
        max_bytes: int,
    ) -> tuple[ImageUrl | None, int, int]:
        """Mirror one reference; return (final value, hit, miss).

        A non-remote value (local or None) is returned unchanged with no
        hit/miss. A remote value that mirrors returns the local reference
        and one hit; one that fails returns the original and one miss —
        the authoritative remote URL is never dropped.
        """
        if current is None or not current.is_remote:
            return current, 0, 0
        mirrored = await self._mirror_one(current, max_bytes)
        if mirrored is None:
            return current, 0, 1
        return mirrored, 1, 0

    async def _mirror_one(self, url: ImageUrl, max_bytes: int) -> ImageUrl | None:
        """Download + store one remote image; return the local reference.

        None means the mirror did not happen — the response was not a
        supported image, or the download/store failed (all logged). The
        caller keeps the remote URL so a later tick can retry.
        """
        try:
            image = await self._downloader.fetch(url.value, max_bytes=max_bytes)
            if not _is_supported_image(image.content_type):
                # A 200 serving HTML (rate-limit/geoblock page) or an
                # svg/unknown type must not be stored over the remote URL.
                _logger.warning(
                    "[artwork-mirror] non-image response; keeping remote URL",
                    url=url.value,
                    content_type=image.content_type,
                )
                return None
            key = ArtworkKey.for_content(
                image.content,
                content_type=image.content_type,
                source_url=url.value,
            )
            served = await self._storage.save(
                content=image.content,
                content_type=image.content_type,
                key=str(key),
            )
            return ImageUrl(served)
        except GatewayException as exc:
            _logger.warning(
                "[artwork-mirror] download failed; keeping remote URL",
                url=url.value,
                error=str(exc),
            )
            return None
        except OSError as exc:
            _logger.warning(
                "[artwork-mirror] storage failed; keeping remote URL",
                url=url.value,
                error=str(exc),
            )
            return None


def _is_supported_image(content_type: str | None) -> bool:
    """Whether a response content type is an artwork image we will store."""
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() in SUPPORTED_ARTWORK_CONTENT_TYPES


__all__ = ["ArtworkMirrorJob"]
