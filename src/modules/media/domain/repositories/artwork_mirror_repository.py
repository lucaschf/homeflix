"""Artwork-mirror role interfaces (ADR-033).

Role-interfaces carved out of the movie/series catalog god-repositories:
the narrow contract the artwork-mirror job (ADR-029) depends on. A movie
or series row is *mirrorable* when one of its artwork columns still holds a
remote provider URL; the job finds those rows and rewrites just the artwork
columns without round-tripping the aggregate (which a full ``save`` would
risk persisting with unloaded children).

The concrete SQLAlchemy repository implements these alongside the catalog
role against the same table (ADR-033 §Decisão). When the artwork subdomain
is extracted (ADR-032), this file moves with it.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.modules.media.domain.value_objects import (
    ArtworkColumns,
    EpisodeId,
    MovieId,
    SeasonId,
    SeriesId,
)


@dataclass(frozen=True)
class RemoteArtworkRow:
    """Lightweight projection of a title's artwork references.

    Used by the artwork-mirror job (ADR-029) to find titles whose
    poster/backdrop/logo is still a remote provider URL and update just
    those columns directly — without loading the aggregate, which a full
    ``save`` would risk persisting with unloaded children (file variants,
    seasons). ``media_id`` is the external id (``mov_xxx`` / ``ser_xxx`` /
    ``ssn_xxx`` / ``epi_xxx``); ``artwork`` carries the references as
    ``ImageUrl`` values, so ``.is_remote`` is available without re-parsing
    strings. Reused across movies, series, seasons, and episodes.
    """

    media_id: str
    artwork: ArtworkColumns


class MovieArtworkMirrorRepository(ABC):
    """Artwork-mirror operations over the ``movies`` table."""

    @abstractmethod
    async def find_with_remote_artwork(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` movies with a still-remote artwork URL.

        A row is returned when any of ``poster_path`` / ``backdrop_path``
        / ``logo_path`` is still an ``http(s)`` provider URL (not yet
        mirrored). Soft-deleted rows are excluded and results are ordered
        by id so the mirror job makes steady forward progress.
        """
        ...

    @abstractmethod
    async def update_movie_artwork(self, movie_id: MovieId, artwork: ArtworkColumns) -> None:
        """Set the three artwork columns directly (mirror job).

        A targeted column update rather than an aggregate ``save`` so the
        mirror job never risks persisting the movie with unloaded file
        variants. ``artwork`` carries the final value for every column
        (the mirrored local reference where one was produced, the
        original value otherwise).
        """
        ...


class SeriesArtworkMirrorRepository(ABC):
    """Artwork-mirror operations over ``series`` / ``seasons`` / ``episodes``."""

    @abstractmethod
    async def find_with_remote_artwork(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` series with a still-remote artwork URL.

        Mirror of ``MovieArtworkMirrorRepository.find_with_remote_artwork``
        over series ``poster_path`` / ``backdrop_path`` / ``logo_path``.
        Season posters and episode stills are handled separately.
        """
        ...

    @abstractmethod
    async def update_series_artwork(self, series_id: SeriesId, artwork: ArtworkColumns) -> None:
        """Set the three artwork columns for one series by external id.

        A targeted column update rather than an aggregate ``save`` so the
        mirror job never risks persisting the series with its seasons and
        episodes unloaded. ``artwork`` carries the final value for every
        column.
        """
        ...

    @abstractmethod
    async def find_seasons_with_remote_poster(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` seasons whose poster is still a remote URL.

        ``RemoteArtworkRow.media_id`` is the season external id (``ssn_xxx``)
        and only ``artwork.poster`` is populated — seasons carry no
        backdrop/logo column.
        """
        ...

    @abstractmethod
    async def update_season_artwork(self, season_id: SeasonId, artwork: ArtworkColumns) -> None:
        """Set a single season's poster column by external id.

        Direct column update on the ``seasons`` table — the mirror job
        never round-trips the ``Series`` aggregate. Only ``artwork.poster``
        is written; the other fields are ignored (no such columns).
        """
        ...

    @abstractmethod
    async def find_episodes_with_remote_thumbnail(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` episodes whose still is still a remote URL.

        ``RemoteArtworkRow.media_id`` is the episode external id
        (``epi_xxx``) and only ``artwork.still`` is populated — the
        episode still is its single mirrorable image. Soft-deleted
        episodes are excluded.
        """
        ...

    @abstractmethod
    async def update_episode_thumbnail(
        self, episode_id: EpisodeId, artwork: ArtworkColumns
    ) -> None:
        """Set a single episode's still (``thumbnail_path``) by external id.

        Direct column update on the ``episodes`` table — no aggregate
        round-trip. Only ``artwork.still`` is written.
        """
        ...


__all__ = [
    "MovieArtworkMirrorRepository",
    "RemoteArtworkRow",
    "SeriesArtworkMirrorRepository",
]
