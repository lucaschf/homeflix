"""Port for resolving per-language TMDB titles (cross-BC, ADR-009).

Catalog Requests needs the localized title of a TMDB entry that is not
yet in the local catalog, so it can snapshot every supported language
at request-creation time. The capability lives in the Media BC (it owns
the TMDB client); this port is the seam the Media adapter implements.
"""

from abc import ABC, abstractmethod

from src.shared_kernel.value_objects import MediaType


class LocalizedTitleProviderPort(ABC):
    """Resolves ``{lang: title}`` for a TMDB id across supported locales."""

    @abstractmethod
    async def get_titles(self, tmdb_id: int, media_type: MediaType) -> dict[str, str]:
        """Return per-language titles for the TMDB entry.

        Args:
            tmdb_id: TMDB numeric id of the title.
            media_type: Whether the id refers to a movie or a series.

        Returns:
            A ``{bcp47_tag: title}`` mapping covering the configured
            supported locales that have a TMDB translation. Best-effort:
            an empty dict on any provider/network failure so request
            creation never fails on a flaky TMDB.
        """
        raise NotImplementedError


__all__ = ["LocalizedTitleProviderPort"]
