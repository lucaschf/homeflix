"""Shared best-effort fetch of a TMDB per-language title snapshot.

Both request-creation entry points ("Solicitar inclusão" and "Avisar
quando chegar") snapshot the localized title once at creation. The fetch
is best-effort: a TMDB/network failure must never fail the user action,
so it degrades to an empty mapping and the entity falls back to the
plain ``title`` snapshot.
"""

import logging

from src.modules.catalog_requests.application.ports import LocalizedTitleProviderPort
from src.shared_kernel.value_objects import MediaType

_logger = logging.getLogger(__name__)


async def resolve_localized_titles(
    provider: LocalizedTitleProviderPort,
    tmdb_id: int,
    media_type: MediaType,
) -> dict[str, str]:
    """Return ``{lang: title}`` from TMDB, or ``{}`` on any failure."""
    try:
        return await provider.get_titles(tmdb_id, media_type)
    except Exception:  # title localization is best-effort — never fail the action
        _logger.warning(
            "Localized title fetch failed for tmdb/%s/%s; falling back to snapshot",
            media_type.value,
            tmdb_id,
            exc_info=True,
        )
        return {}


__all__ = ["resolve_localized_titles"]
