"""Cross-BC read port — reads catalog-request state from Media."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogRequestStatus:
    """Catalog-request snapshot for a single TMDB title.

    The Media BC is the consumer here: it stitches per-title
    catalog-request status into the Collection Detail response so
    the FilmRow can render the right CTA (Solicitar inclusão vs.
    Pedido registrado vs. Avisar quando chegar) without N+1 lookups.

    Attributes:
        is_requested: ``True`` when a request row exists for this
            ``tmdb_id``. Single-user platform, so the existence of
            a row already means "the user wants this".
        notify_on_arrival: ``True`` when the user has subscribed
            to the arrival notification.
        is_fulfilled: ``True`` once the title has been added to
            the catalog. Pending requests stay ``False``.
    """

    is_requested: bool
    notify_on_arrival: bool
    is_fulfilled: bool


class CatalogRequestLookupPort(ABC):
    """Batch lookup of catalog-request status for movie TMDB ids.

    Defined here in the consuming Media BC; implemented as an ACL
    adapter inside the Catalog Requests BC so Media stays free of
    direct cross-BC imports (ADR-009).

    Today the port only handles movies — series-level requests
    aren't surfaced anywhere on the UI yet — but the signature is
    ``movie``-suffixed so a future ``get_for_series_tmdb_ids``
    can land additively.
    """

    @abstractmethod
    async def get_for_movie_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
    ) -> dict[int, CatalogRequestStatus]:
        """Return per-id request status.

        Args:
            tmdb_ids: TMDB movie ids whose status the caller needs.
                An empty input returns an empty dict without any
                round-trip to the Catalog Requests BC.

        Returns:
            Mapping of ``tmdb_id`` to ``CatalogRequestStatus`` for
            every id that has a row in Catalog Requests. Ids
            without a row are simply absent — callers default to
            "no request, no subscription" for those.
        """


__all__ = ["CatalogRequestLookupPort", "CatalogRequestStatus"]
