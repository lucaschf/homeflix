"""DTOs for the catalog-request use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.catalog_requests.domain.entities import CatalogRequest
    from src.modules.catalog_requests.domain.value_objects import RequestedMediaType


@dataclass(frozen=True)
class CreateCatalogRequestInput:
    """Input for ``RequestCatalogInclusionUseCase``.

    Attributes:
        tmdb_id: TMDB numeric id of the title to request.
        media_type: Whether the target is a movie or a series.
        collection_tmdb_id: Optional franchise id that surfaced this
            request (set when the user clicks "Solicitar inclusão"
            from a Collection Detail page).
        notify_on_arrival: Subscribe to the arrival notification at
            the same time. Defaults to ``False`` so the simpler
            "register a request" path stays minimal.
    """

    tmdb_id: int
    media_type: RequestedMediaType
    collection_tmdb_id: int | None = None
    notify_on_arrival: bool = False


@dataclass(frozen=True)
class SubscribeCatalogNotificationInput:
    """Input for ``SubscribeCatalogNotificationUseCase``."""

    tmdb_id: int
    media_type: RequestedMediaType
    collection_tmdb_id: int | None = None


@dataclass(frozen=True)
class CatalogRequestOutput:
    """Output representation of a catalog request.

    Attributes:
        id: External request id (``req_xxx``).
        tmdb_id: TMDB numeric id of the requested title.
        media_type: ``"movie"`` or ``"series"``.
        collection_tmdb_id: Originating TMDB collection id, if any.
        notify_on_arrival: Whether the user opted in to a notification.
        is_fulfilled: ``True`` when the title is already in the catalog.
        requested_at: ISO-8601 creation timestamp.
        fulfilled_at: ISO-8601 fulfillment timestamp, or ``None``.
    """

    id: str
    tmdb_id: int
    media_type: str
    collection_tmdb_id: int | None
    notify_on_arrival: bool
    is_fulfilled: bool
    requested_at: str
    fulfilled_at: str | None

    @classmethod
    def from_entity(cls, entity: CatalogRequest) -> CatalogRequestOutput:
        """Build the DTO from a domain ``CatalogRequest`` aggregate."""
        return cls(
            id=str(entity.id),
            tmdb_id=entity.tmdb_id,
            media_type=entity.media_type.value,
            collection_tmdb_id=entity.collection_tmdb_id,
            notify_on_arrival=entity.notify_on_arrival,
            is_fulfilled=entity.is_fulfilled,
            requested_at=entity.requested_at.isoformat(),
            fulfilled_at=entity.fulfilled_at.isoformat() if entity.fulfilled_at else None,
        )


__all__ = [
    "CatalogRequestOutput",
    "CreateCatalogRequestInput",
    "SubscribeCatalogNotificationInput",
]
