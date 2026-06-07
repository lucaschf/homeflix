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

from src.shared_kernel.value_objects import CollectionMediaType
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
    """

    media_id: str
    media_type: CollectionMediaType
    title: str
    poster_path: str | None


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
    ) -> dict[tuple[CollectionMediaType, str], MediaSummary]:
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
