"""Port for looking up display metadata of media items from the Media BC.

Collections (watchlist, custom lists) embed the title and poster of
the referenced movies/series in their list responses. This port is
the only surface through which Collections reaches into the Media
catalog. The adapter lives in ``collections.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


@dataclass(frozen=True)
class MediaSummary:
    """Minimal media display data needed by Collections.

    Attributes:
        media_id: External id (``mov_xxx`` or ``ser_xxx``).
        media_type: Whether the referenced media is a movie or series.
        title: Already-localized title (resolved server-side using the
            ``lang`` argument passed to ``get_many``).
        poster_path: Absolute or relative poster URL, or ``None`` when
            the source has no poster.
        year: Release year (movie) or first-air year (series), or
            ``None`` when unknown.
        runtime_seconds: Runtime in seconds. Set for movies; ``None``
            for series (their runtime is per-episode and not surfaced
            here yet).
        genres: Localized genre names, ordered. Empty when none.
        resolution: Best available resolution label (e.g. ``"4K"``,
            ``"1080p"``). Set for movies with files; ``None`` for series
            (episode-derived, deferred).
        hdr: Whether the best file carries an HDR format. Movies only.
    """

    media_id: str
    media_type: MediaType
    title: str
    poster_path: str | None
    year: int | None = None
    runtime_seconds: int | None = None
    genres: tuple[str, ...] = ()
    resolution: str | None = None
    hdr: bool = False


class MediaLookupPort(ABC):
    """Batch lookup of media display metadata by id + type.

    The port deliberately takes two parallel id lists instead of a
    single mixed list so the adapter can issue one query per table.
    Keeping the argument signature flat (no wrapping object) matches
    the existing use-case code style.
    """

    @abstractmethod
    async def get_many(
        self,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        lang: str,
    ) -> dict[tuple[MediaType, str], MediaSummary]:
        """Resolve metadata for the given movies and series.

        Args:
            movie_ids: Typed external movie ids.
            series_ids: Typed external series ids.
            lang: Language code used to localize titles.

        Returns:
            Map keyed by ``(media_type, media_id)``. Ids that don't
            resolve to an entity are simply absent from the map — the
            use case decides how to handle the gap.
        """
        ...


__all__ = ["MediaLookupPort", "MediaSummary"]
