"""ACL adapter exposing TMDB localized titles to the Catalog Requests BC.

Catalog Requests owns ``LocalizedTitleProviderPort`` (it needs the title
of a not-yet-in-catalog TMDB entry in every supported language). The
capability lives here in Media, which owns the TMDB client — so this
provider-side adapter implements that port (ADR-009), mirroring how
``CatalogRequestLookupAdapter`` implements Media's port from the other
side.
"""

from src.modules.catalog_requests.application.ports import LocalizedTitleProviderPort
from src.modules.media.infrastructure.metadata.tmdb_client import TmdbClient
from src.shared_kernel.value_objects import MediaType


class TmdbLocalizedTitleAdapter(LocalizedTitleProviderPort):
    """Resolves per-language TMDB titles via the Media TMDB client."""

    def __init__(self, tmdb_client: TmdbClient) -> None:
        """Initialize the adapter.

        Args:
            tmdb_client: The Media TMDB client used to fetch the
                ``/translations`` payload.
        """
        self._tmdb = tmdb_client

    async def get_titles(self, tmdb_id: int, media_type: MediaType) -> dict[str, str]:
        """Return ``{lang: title}`` for the configured supported locales."""
        return await self._tmdb.get_translated_titles(tmdb_id, media_type)


__all__ = ["TmdbLocalizedTitleAdapter"]
