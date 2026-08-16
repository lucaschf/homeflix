"""DTOs for the catalog-request use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.catalog_requests.domain.entities import CatalogRequest
    from src.shared_kernel.value_objects import MediaType


@dataclass(frozen=True)
class CreateCatalogRequestInput:
    """Input for ``RequestCatalogInclusionUseCase``.

    Attributes:
        tmdb_id: TMDB numeric id of the title to request.
        media_type: Whether the target is a movie or a series.
        title: Snapshot of the TMDB title at request time. Optional
            so older clients (and programmatic seeds) keep working,
            but the Collection Detail page sends it in so the admin
            queue can render the title inline.
        collection_tmdb_id: Optional franchise id that surfaced this
            request (set when the user clicks "Solicitar inclusão"
            from a Collection Detail page).
        notify_on_arrival: Subscribe to the arrival notification at
            the same time. Defaults to ``False`` so the simpler
            "register a request" path stays minimal.
    """

    tmdb_id: int
    media_type: MediaType
    title: str | None = None
    poster_url: str | None = None
    requester_user_id: str | None = None
    collection_tmdb_id: int | None = None
    notify_on_arrival: bool = False


@dataclass(frozen=True)
class SubscribeCatalogNotificationInput:
    """Input for ``SubscribeCatalogNotificationUseCase``."""

    tmdb_id: int
    media_type: MediaType
    title: str | None = None
    poster_url: str | None = None
    requester_user_id: str | None = None
    collection_tmdb_id: int | None = None


@dataclass(frozen=True)
class UnsubscribeCatalogNotificationInput:
    """Input for ``UnsubscribeCatalogNotificationUseCase``.

    The "Você será avisado → desligar" toggle on the consumer side.
    Identifies the title by its TMDB target (every member entry point
    speaks TMDB ids) plus the acting user, so we drop only that user's
    subscription and leave the request — and everyone else's
    subscriptions — in place.

    Attributes:
        tmdb_id: TMDB numeric id of the title to stop following.
        media_type: Whether the target is a movie or a series.
        user_id: External id (``usr_xxx``) of the user unsubscribing.
    """

    tmdb_id: int
    media_type: MediaType
    user_id: str


@dataclass(frozen=True)
class DismissCatalogRequestInput:
    """Input for ``DismissCatalogRequestUseCase``.

    The admin "Dismiss" action removes a pending request from the
    queue when the household no longer wants to track it (e.g. the
    title becomes available on a service the household uses, or the
    initial request was a misclick on an obscure tmdb id).

    Attributes:
        request_id: External catalog-request id (``req_xxx``).
    """

    request_id: str


@dataclass(frozen=True)
class CatalogRequestOutput:
    """Output representation of a catalog request.

    Attributes:
        id: External request id (``req_xxx``).
        tmdb_id: TMDB numeric id of the requested title.
        media_type: ``"movie"`` or ``"series"``.
        title: Snapshot of the title taken at request time. ``None``
            on legacy rows created before the column existed.
        poster_url: Snapshot of the TMDB poster URL, or ``None`` when
            not captured / not yet backfilled.
        requester_user_id: External id (``usr_xxx``) of the user who
            registered the request. ``None`` on legacy rows.
        collection_tmdb_id: Originating TMDB collection id, if any.
        source: ``"user"`` or ``"household"`` — who put it in the queue.
        notify_on_arrival: Whether the user opted in to a notification.
        is_fulfilled: ``True`` when the title is already in the catalog.
        status: Derived ``"pending"`` / ``"fulfilled"`` (honest, thin).
        requested_at: ISO-8601 creation timestamp.
        fulfilled_at: ISO-8601 fulfillment timestamp, or ``None``.
    """

    id: str
    tmdb_id: int
    media_type: str
    title: str | None
    poster_url: str | None
    requester_user_id: str | None
    collection_tmdb_id: int | None
    source: str
    notify_on_arrival: bool
    is_fulfilled: bool
    status: str
    requested_at: str
    fulfilled_at: str | None

    @classmethod
    def from_entity(cls, entity: CatalogRequest, lang: str | None = None) -> CatalogRequestOutput:
        """Build the DTO from a domain ``CatalogRequest`` aggregate.

        Args:
            entity: The request aggregate to serialize.
            lang: When given, the title is resolved in that language via
                the per-language snapshot (``get_title``); when ``None``
                the raw ``title`` snapshot is returned as-is (the create
                response echoes back what the client sent).
        """
        return cls(
            id=str(entity.id),
            tmdb_id=entity.tmdb_id.value,
            media_type=entity.media_type.value,
            title=entity.get_title(lang) if lang is not None else entity.title,
            poster_url=entity.poster_url.value if entity.poster_url else None,
            requester_user_id=entity.requester_user_id,
            collection_tmdb_id=entity.collection_tmdb_id.value
            if entity.collection_tmdb_id
            else None,
            source=entity.source.value,
            notify_on_arrival=entity.notify_on_arrival,
            is_fulfilled=entity.is_fulfilled,
            status=entity.status.value,
            requested_at=entity.requested_at.isoformat(),
            fulfilled_at=entity.fulfilled_at.isoformat() if entity.fulfilled_at else None,
        )


@dataclass(frozen=True)
class CatalogRequestFeedItem:
    """A pending request enriched for the member "Em breve" feed.

    Wraps the base request DTO with the two per-view extras the
    consumer page needs (ADR-022): how many people are waiting and
    whether the caller is one of them. The route flattens this onto
    the base fields for the wire.

    Attributes:
        request: The underlying request DTO (id, title, status, …).
        subscriber_count: Active subscribers — the "{N} pessoas
            aguardando" figure.
        is_subscribed: Whether the calling user follows this title.
    """

    request: CatalogRequestOutput
    subscriber_count: int
    is_subscribed: bool


@dataclass(frozen=True)
class AdminCatalogRequestItem:
    """A pending request enriched for the admin queue.

    Like the member feed item but without the per-caller
    ``is_subscribed`` flag — the admin sees the aggregate count, not
    their own subscription state.

    Attributes:
        request: The underlying request DTO (carries source + status).
        subscriber_count: Active subscribers — the "Inscritos" column.
    """

    request: CatalogRequestOutput
    subscriber_count: int


@dataclass(frozen=True)
class IncludeCatalogRequestInput:
    """Input for ``IncludeCatalogRequestUseCase`` — admin "mark as included".

    Attributes:
        request_id: External catalog-request id (``req_xxx``).
    """

    request_id: str


__all__ = [
    "AdminCatalogRequestItem",
    "CatalogRequestFeedItem",
    "CatalogRequestOutput",
    "CreateCatalogRequestInput",
    "DismissCatalogRequestInput",
    "IncludeCatalogRequestInput",
    "SubscribeCatalogNotificationInput",
    "UnsubscribeCatalogNotificationInput",
]
