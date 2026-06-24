"""Cross-BC port — publish in-app notifications from catalog_requests.

The Catalog Requests BC is the *consumer* here: when the
auto-fulfillment loop closes a request, it wants to ping the
user who registered it. The Notifications BC is the provider.
Per ADR-009 the port lives in the consumer's application layer
and is implemented as an ACL adapter inside the Notifications
BC, so Catalog Requests stays free of a direct import on
Notifications' domain types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


@dataclass(frozen=True)
class CatalogArrivalNotification:
    """Payload for the "title is now available" notification.

    Carries only the fields the receiving renderer needs: the
    pre-formatted title (so the publisher doesn't have to know
    the user's locale), the TMDB anchor (so the click-through
    can deep-link), and the newly-minted media id (so the
    landing page resolves without an extra TMDB→media lookup).

    Attributes:
        recipient_user_id: External id (``usr_xxx``) of the
            user who registered the request and should now be
            pinged. The handler short-circuits when this is
            ``None`` (legacy / anonymous request), so the
            adapter never receives a missing value.
        title: Display title rendered in the notification row.
            Sourced from the snapshot stored on the catalog
            request at registration time, so the publisher
            doesn't need a TMDB round-trip here.
        tmdb_id: TMDB id of the fulfilled title — kept on the
            payload so the frontend can fall back to a TMDB
            link if the local media id is unavailable.
        media_id: Typed external id of the local media row
            (``MovieId`` / ``SeriesId``) the request was fulfilled
            by. Used as the primary click-through target. ``None`` for
            a manual "mark as included" with no resolved local title
            (ADR-022) — the notification still fires, the renderer just
            falls back to search instead of a precise deep-link.
        media_type: ``"movie"`` or ``"series"`` so the renderer
            picks the right deep-link path.
    """

    recipient_user_id: str
    title: str
    tmdb_id: int
    media_id: MovieId | SeriesId | None
    media_type: str


class NotificationPublisherPort(ABC):
    """Dispatch a notification triggered from Catalog Requests.

    Defined in the consumer BC so Catalog Requests doesn't take a
    runtime dependency on Notifications' domain types — only on
    this small interface and its plain DTO. The composition root
    wires a concrete adapter that calls the Notifications
    ``CreateNotificationUseCase``.
    """

    @abstractmethod
    async def publish_catalog_arrival(
        self,
        notification: CatalogArrivalNotification,
    ) -> None:
        """Publish a "title now available" notification.

        Fire-and-forget from the caller's perspective: failures
        must not propagate back into the event handler, otherwise
        a transient notifications outage would block the catalog
        request from being marked fulfilled. The adapter swallows
        and logs.
        """


__all__ = ["CatalogArrivalNotification", "NotificationPublisherPort"]
