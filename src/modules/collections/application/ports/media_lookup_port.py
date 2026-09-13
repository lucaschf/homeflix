"""Port for looking up display metadata of media items from the Media BC.

Collections (watchlist, custom lists) embed the title and poster of
the referenced movies/series in their list responses, and refuse to
save a title the caller's profile cannot see. This port is the only
surface through which Collections reaches into the Media catalog. The
adapter lives in ``collections.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
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
        library_id: External id (``lib_xxx``) of the library the media
            lives in, or ``None`` when unknown. Consumed by every list
            read to filter items through the caller's per-profile
            library access (ADR-010) — a list may reference titles the
            caller's profile can't see.
        minimum_age: Age the title requires, or ``None`` when it carries
            no determinable certification (read as adult by
            ``AgeRating.allows``). Consumed by every list read to apply
            the caller's maturity limit (ADR-035). Keyword-only with no
            default, so a construction that forgets it fails instead of
            silently hiding the title from every limited profile.
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
    library_id: str | None = None
    minimum_age: AgeRating | None = field(kw_only=True)


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
            use case decides how to handle the gap. No viewing policy is
            applied: a title the caller can't see is still returned, so
            the use case can tell it apart from one that was removed.
        """
        ...

    @abstractmethod
    async def find_visible_titles(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        policy: ViewingPolicy,
    ) -> frozenset[str]:
        """Answer which of these titles the policy lets the caller see.

        Unlike :meth:`get_many`, the policy is applied on both axes, and a
        title that does not exist comes back the same way as one the
        policy hides — absent — so a write gated on this answer cannot
        tell the two apart (ADR-035).

        Args:
            movie_ids: Movies to check.
            series_ids: Series to check.
            policy: The caller's viewing policy, applied on both axes.

        Returns:
            External ids (``mov_xxx`` / ``ser_xxx``) of the visible
            titles. A title that does not exist, is soft-deleted, or is
            denied by the policy is absent.
        """
        ...


__all__ = ["MediaLookupPort", "MediaSummary"]
